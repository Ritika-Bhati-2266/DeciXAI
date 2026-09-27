from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import math
import re

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from utils.xlsx_loader import read_excel_flexible

try:
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline as ImbPipeline
except Exception:  # pragma: no cover - optional until dependency install
    SMOTE = None
    ImbPipeline = None

try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional until dependency install
    XGBClassifier = None


ROOT = Path(__file__).resolve().parent
DATASETS_DIR = ROOT / 'datasets'
MODELS_DIR = ROOT / 'models'
MODELS_DIR.mkdir(exist_ok=True)

STOPWORDS = {
    'and', 'or', 'with', 'for', 'the', 'a', 'an', 'to', 'of', 'in', 'on', 'using',
    'skills', 'skill', 'experience', 'knowledge', 'work', 'working', 'ability',
    'development', 'developer', 'engineer', 'software', 'data', 'science', 'role',
    'roles', 'job', 'jobs', 'good', 'strong', 'basic', 'advanced',
}

SKILL_PATTERNS = {
    'python': ['python'],
    'sql': ['sql', 'mysql', 'postgres', 'postgresql'],
    'statistics': ['statistics', 'statistical', 'probability'],
    'machine learning': ['machine learning', 'ml'],
    'deep learning': ['deep learning', 'neural network'],
    'pandas': ['pandas'],
    'numpy': ['numpy'],
    'power bi': ['power bi'],
    'tableau': ['tableau'],
    'excel': ['excel'],
    'spark': ['spark', 'pyspark'],
    'java': ['java'],
    'javascript': ['javascript', 'js'],
    'react': ['react'],
    'node': ['node', 'nodejs', 'node.js'],
    'backend': ['backend', 'api', 'microservice', 'server'],
    'frontend': ['frontend', 'ui', 'css', 'html'],
    'dsa': ['dsa', 'data structures', 'algorithms'],
    'system design': ['system design'],
    'git': ['git', 'github'],
    'testing': ['testing', 'unit test', 'pytest', 'qa'],
    'cloud': ['cloud', 'aws', 'azure', 'gcp'],
    'devops': ['devops', 'docker', 'kubernetes', 'ci/cd', 'jenkins'],
    'cybersecurity': ['cybersecurity', 'security', 'soc', 'penetration testing'],
    'product': ['product', 'roadmap', 'stakeholder', 'market research'],
}

CAREER_PATHS = {
    'data_science': [
        'data scientist', 'data science', 'machine learning engineer', 'machine learning',
        'ml engineer', 'ai engineer', 'data analyst', 'business intelligence',
        'bi analyst', 'analytics',
    ],
    'software_development': [
        'software engineer', 'software developer', 'full stack', 'frontend', 'backend',
        'web developer', 'application developer', 'sde', 'programmer', 'mobile developer',
        'ios developer', 'android developer', 'game developer',
    ],
    'cloud_devops': [
        'devops', 'site reliability', 'sre', 'cloud engineer', 'platform engineer',
        'aws engineer', 'azure engineer', 'gcp engineer', 'infrastructure engineer',
    ],
    'cybersecurity': [
        'security analyst', 'cybersecurity', 'soc analyst', 'security engineer',
        'penetration tester', 'ethical hacker', 'information security',
    ],
    'product_management': [
        'product manager', 'product owner', 'program manager', 'business analyst',
        'product analyst', 'growth hacker', 'technical product manager',
        'project manager', 'project management',
    ],
    'ui_ux_design': [
        'ui designer', 'ux designer', 'user experience', 'user interface', 'design',
        'graphic designer', 'interaction designer',
    ],
    'data_engineering': [
        'data engineer', 'analytics engineer', 'big data engineer', 'big data',
        'hadoop', 'spark', 'etl developer', 'etl engineer',
    ],
    'marketing': [
        'marketing', 'digital marketing', 'seo', 'content marketing', 'brand manager',
    ],
    'finance': [
        'finance', 'financial analyst', 'investment banker', 'quantitative analyst',
    ],
    'consulting': [
        'consultant', 'management consultant', 'strategy consultant',
    ],
}

PATH_DISPLAY_NAMES = {
    'data_science': 'Data Science',
    'software_development': 'Software Development',
    'cloud_devops': 'Cloud / DevOps',
    'cybersecurity': 'Cybersecurity',
    'product_management': 'Product Management',
    'ui_ux_design': 'UI/UX Design',
    'data_engineering': 'Data Engineering',
    'marketing': 'Marketing',
    'finance': 'Finance',
    'consulting': 'Consulting',
}

EXPECTED_CAREER_CLASSES = list(PATH_DISPLAY_NAMES.keys())
CAREER_PATH_PRIORITY = {path: index for index, path in enumerate(EXPECTED_CAREER_CLASSES)}
ONET_TEXT_DIR = DATASETS_DIR / 'career' / 'db_29_0_text'


def safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        if isinstance(value, str):
            cleaned = value.strip().replace(',', '')
            if not cleaned:
                return default
            return float(cleaned)
        return float(value)
    except Exception:
        return default


def normalize_text(value) -> str:
    return re.sub(r'\s+', ' ', str(value or '').lower()).strip()


def split_items(text):
    if pd.isna(text):
        return []
    parts = re.split(
        r'[;,|]|\band\b|(?<!\bci)(?<!\bui)(?<!\bpl)(?<!\btcp)(?<!\ba)\/(?!cd\b)(?!ux\b)(?!sql\b)(?!ip\b)(?!b\b)',
        str(text),
        flags=re.IGNORECASE,
    )
    return [part.strip().lower() for part in parts if part and part.strip()]


def tokenize(value: str) -> list[str]:
    tokens = re.findall(r'[a-z][a-z0-9+#.-]{1,}', normalize_text(value))
    return [token for token in tokens if token not in STOPWORDS]


def extract_skill_hits(text: str) -> list[str]:
    lowered = normalize_text(text)
    hits = []
    for skill, patterns in SKILL_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            hits.append(skill)
    return hits


def map_interest(text):
    value = normalize_text(text)
    # Cloud/DevOps is treated as "technical" in this app (not "data").
    if any(word in value for word in ['cloud', 'devops', 'sre', 'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform']):
        return 'technical'
    if any(word in value for word in ['data', 'analytic', 'analysis', 'ai']):
        return 'data'
    if any(word in value for word in ['manage', 'business', 'leader', 'finance', 'sales', 'market', 'product']):
        return 'management'
    return 'technical'


def map_market(text):
    value = normalize_text(text)
    if any(word in value for word in ['enterprise', 'saas', 'b2b', 'fintech', 'hrtech', 'deeptech']):
        return 'enterprise'
    return 'consumer'


def map_sector(text):
    value = normalize_text(text)
    if any(word in value for word in ['health', 'medical', 'hospital', 'nutrition', 'jsy', 'mmr', 'imr']):
        return 'healthcare'
    if any(word in value for word in ['education', 'school', 'student', 'teacher', 'learning', 'aicte']):
        return 'education'
    return 'infrastructure'


def parse_money_to_usd(value):
    text = str(value).strip()
    if not text or text.lower() == 'nan':
        return np.nan
    cleaned = re.sub(r'[^0-9.]', '', text)
    if not cleaned:
        return np.nan
    return safe_float(cleaned, np.nan)


def parse_rupee_amount(text):
    value = str(text)
    match = re.search(r'([0-9,]+(?:\.[0-9]+)?)', value)
    if not match:
        return np.nan
    return safe_float(match.group(1).replace(',', ''), np.nan)


def parse_experience_range(text):
    numbers = [safe_float(num, np.nan) for num in re.findall(r'[0-9]+(?:\.[0-9]+)?', str(text))]
    numbers = [num for num in numbers if not math.isnan(num)]
    if not numbers:
        return np.nan
    return float(sum(numbers) / len(numbers))


def normalize_course(text):
    value = normalize_text(text)
    if any(word in value for word in ['b.tech', 'b.e', 'computer', 'information', 'it', 'software']):
        return 'engineering'
    if any(word in value for word in ['b.sc', 'science', 'mathematics', 'physics']):
        return 'science'
    if any(word in value for word in ['bca', 'mca']):
        return 'computer_applications'
    if any(word in value for word in ['business', 'commerce', 'management', 'mba']):
        return 'business'
    return 'general'


def classify_career_path(text):
    lowered = normalize_text(text)
    best_path = None
    best_score = 0.0
    best_specificity = 0.0

    for path_name, patterns in CAREER_PATHS.items():
        score = 0.0
        matched_chars = 0
        match_count = 0
        for pattern in patterns:
            escaped = re.escape(pattern).replace(r'\ ', r'[\s/-]+')
            if re.search(rf'(?<!\w){escaped}(?!\w)', lowered):
                score += 1.0 + min(len(pattern.split()) * 0.15, 0.45)
                matched_chars += len(pattern)
                match_count += 1
        specificity = matched_chars + (match_count * 0.5)
        if score > best_score or (score == best_score and specificity > best_specificity):
            best_path = path_name
            best_score = score
            best_specificity = specificity

    return best_path if best_score >= 1.0 else None


def build_career_label_audit(posting_labels, salary_labels, learned_classes):
    expected_set = set(EXPECTED_CAREER_CLASSES)
    learned_set = set(learned_classes)

    return {
        'expected_classes': EXPECTED_CAREER_CLASSES,
        'posting_label_counts': {key: int(value) for key, value in posting_labels.value_counts(dropna=False).items()},
        'salary_label_counts': {key: int(value) for key, value in salary_labels.value_counts(dropna=False).items()},
        'learned_classes': list(learned_classes),
        'missing_expected_classes': sorted(expected_set - learned_set),
        'unexpected_classes': sorted(learned_set - expected_set),
    }


def build_profile_metadata(dataset, y, numeric_features, categorical_features):
    metadata = {
        'numeric': {},
        'categorical': {},
    }
    positive = dataset.loc[y == 1].copy()
    negative = dataset.loc[y == 0].copy()

    for feature in numeric_features:
        series = dataset[feature].astype(float)
        pos_series = positive[feature].astype(float) if feature in positive else pd.Series(dtype=float)
        neg_series = negative[feature].astype(float) if feature in negative else pd.Series(dtype=float)
        metadata['numeric'][feature] = {
            'overall_median': round(float(series.median()), 4),
            'positive_median': round(float(pos_series.median()), 4) if not pos_series.empty else None,
            'negative_median': round(float(neg_series.median()), 4) if not neg_series.empty else None,
            'p75': round(float(series.quantile(0.75)), 4),
            'p25': round(float(series.quantile(0.25)), 4),
            'positive_p25': round(float(pos_series.quantile(0.25)), 4) if not pos_series.empty else None,
            'positive_p75': round(float(pos_series.quantile(0.75)), 4) if not pos_series.empty else None,
        }

    for feature in categorical_features:
        rates = (
            dataset.assign(_target=y.astype(int))
            .groupby(feature, dropna=False)['_target']
            .agg(['mean', 'count'])
            .reset_index()
            .sort_values(['mean', 'count'], ascending=[False, False])
        )
        metadata['categorical'][feature] = [
            {
                'value': '' if pd.isna(row[feature]) else str(row[feature]),
                'success_rate': round(float(row['mean']), 4),
                'count': int(row['count']),
            }
            for _, row in rates.head(10).iterrows()
        ]

    return metadata


def build_tree_pipeline(numeric_features, categorical_features, estimator):
    transformers = [
        ('num', Pipeline([('imputer', SimpleImputer(strategy='median'))]), numeric_features),
    ]
    if categorical_features:
        transformers.append((
            'cat',
            Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent')),
                ('onehot', OneHotEncoder(handle_unknown='ignore')),
            ]),
            categorical_features,
        ))

    steps = [('preprocessor', ColumnTransformer(transformers=transformers))]
    if SMOTE is not None and ImbPipeline is not None:
        steps.append(('smote', SMOTE(random_state=42)))
        steps.append(('model', estimator))
        return ImbPipeline(steps)

    steps.append(('model', estimator))
    return Pipeline(steps)


def train_tree_bundle(domain, dataset, numeric_features, categorical_features, feature_labels):
    X = dataset[numeric_features + categorical_features].copy()
    y = dataset['target'].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y if y.nunique() > 1 else None,
    )

    if XGBClassifier is not None:
        candidates = {
            'xgboost': XGBClassifier(
                n_estimators=120,
                max_depth=4,
                learning_rate=0.08,
                subsample=0.9,
                colsample_bytree=0.9,
                reg_lambda=1.2,
                min_child_weight=2,
                eval_metric='logloss',
                random_state=42,
                n_jobs=1,
                tree_method='hist',
                verbosity=0,
            ),
        }
    else:
        candidates = {
            'extra_trees': ExtraTreesClassifier(
                n_estimators=240,
                max_depth=None,
                min_samples_leaf=2,
                random_state=42,
                class_weight='balanced',
                n_jobs=1,
            ),
            'random_forest': RandomForestClassifier(
                n_estimators=180,
                max_depth=14,
                min_samples_leaf=2,
                random_state=42,
                class_weight='balanced_subsample',
                n_jobs=1,
            ),
        }

    best = None
    best_metrics = None
    best_score = -1.0

    for model_name, estimator in candidates.items():
        pipeline = build_tree_pipeline(numeric_features, categorical_features, estimator)
        pipeline.fit(X_train, y_train)
        predictions = pipeline.predict(X_test)
        probabilities = pipeline.predict_proba(X_test)[:, 1]
        metrics = {
            'model': model_name,
            'accuracy': round(float(accuracy_score(y_test, predictions)), 4),
            'f1': round(float(f1_score(y_test, predictions, zero_division=0)), 4),
            'roc_auc': round(float(roc_auc_score(y_test, probabilities)), 4),
        }
        score = metrics['f1'] * 0.55 + metrics['roc_auc'] * 0.35 + metrics['accuracy'] * 0.10
        if score > best_score:
            best = model_name
            best_metrics = metrics
            best_score = score

    final_pipeline = build_tree_pipeline(
        numeric_features,
        categorical_features,
        candidates[best],
    )
    final_pipeline.fit(X, y)

    return {
        'domain': domain,
        'pipeline': final_pipeline,
        'positive_class': 1,
        'metrics': best_metrics,
        'samples': int(len(dataset)),
        'training_stack': {
            'uses_xgboost': bool(XGBClassifier is not None),
            'uses_smote': bool(SMOTE is not None),
        },
        'features': {
            'numeric': numeric_features,
            'categorical': categorical_features,
        },
        'profiles': build_profile_metadata(dataset, y, numeric_features, categorical_features),
        'feature_labels': feature_labels,
    }


def build_career_dataset():
    df = pd.read_csv(DATASETS_DIR / 'career' / 'career_recommender.csv')
    cgpa_col = 'What was the average CGPA or Percentage obtained in under graduation?'
    skills_col = 'What are your skills ? (Select multiple if necessary)'
    interest_col = 'What are your interests?'
    working_col = 'Are you working?'
    job_col = 'If yes, then what is/was your first Job title in your current field of work? If not applicable, write NA.               '
    masters_col = 'Have you done masters after undergraduation? If yes, mention your field of masters.(Eg; Masters in Mathematics)'
    cert_col = 'If yes, please specify your certificate course title.'
    course_col = 'What was your course in UG?'
    spec_col = 'What is your UG specialization? Major Subject (Eg; Mathematics)'

    out = pd.DataFrame()
    cgpa_raw = df[cgpa_col].apply(lambda x: safe_float(x, 7.0))
    out['cgpa'] = np.where(cgpa_raw > 10, cgpa_raw / 10.0, cgpa_raw).clip(0, 10)
    out['skills_count'] = df[skills_col].apply(lambda x: len(split_items(x)))
    out['projects_count'] = (
        df[cert_col].apply(lambda x: len(split_items(x)))
        + df[working_col].fillna('').astype(str).str.lower().eq('yes').astype(int)
        + df[masters_col].notna().astype(int)
    )
    out['certifications_count'] = df[cert_col].apply(lambda x: len(split_items(x)))
    out['internship_count'] = df[working_col].fillna('').astype(str).str.lower().eq('yes').astype(int)
    out['experience_years'] = out['projects_count'] * 0.5 + out['internship_count']
    out['portfolio_strength'] = out['projects_count'] + out['certifications_count'] + out['internship_count']
    out['skill_project_ratio'] = out['skills_count'] / np.maximum(out['projects_count'], 1)
    out['masters_flag'] = df[masters_col].notna().astype(int)
    out['interest'] = df[interest_col].apply(map_interest)
    out['course_group'] = df[course_col].apply(normalize_course)
    out['specialization_group'] = df[spec_col].apply(normalize_course)

    job_series = df[job_col].fillna('').astype(str).str.strip().str.lower()
    good_job = ~job_series.isin({'', 'na', 'nan', 'student (unemployed)', 'student'})
    out['target'] = (df[working_col].fillna('').astype(str).str.lower().eq('yes') & good_job).astype(int)

    # Enrich readiness training with the Indian Student Placement dataset (if available).
    placement_path = DATASETS_DIR / 'career' / 'Indian_Student_Placement_Dataset_2025.csv'
    if placement_path.exists():
        placement_df = pd.read_csv(placement_path)
        placement_part = pd.DataFrame()
        placement_part['cgpa'] = pd.to_numeric(placement_df.get('cgpa'), errors='coerce').fillna(7.0).clip(0, 10)
        placement_part['projects_count'] = pd.to_numeric(placement_df.get('projects'), errors='coerce').fillna(0).clip(lower=0)
        placement_part['certifications_count'] = pd.to_numeric(placement_df.get('certifications'), errors='coerce').fillna(0).clip(lower=0)
        placement_part['internship_count'] = pd.to_numeric(placement_df.get('internships'), errors='coerce').fillna(0).clip(lower=0)
        coding = pd.to_numeric(placement_df.get('coding_skills'), errors='coerce').fillna(1).clip(1, 10)
        communication = pd.to_numeric(placement_df.get('communication_skills'), errors='coerce').fillna(1).clip(1, 10)
        # Approximate "skills_count" from skill ratings + certifications so it aligns with the existing schema.
        placement_part['skills_count'] = (
            ((coding + communication) / 2.6).round()
            + (placement_part['certifications_count'].clip(0, 5) / 2.0).round()
        ).clip(1, 12)
        placement_part['experience_years'] = (
            placement_part['internship_count'] * 0.6
            + placement_part['projects_count'] * 0.25
        ).clip(lower=0)
        placement_part['portfolio_strength'] = (
            placement_part['projects_count']
            + placement_part['certifications_count']
            + placement_part['internship_count']
        )
        placement_part['skill_project_ratio'] = placement_part['skills_count'] / np.maximum(placement_part['projects_count'], 1)
        placement_part['masters_flag'] = 0
        placement_part['interest'] = 'technical'
        placement_part['course_group'] = placement_df.get('degree', '').apply(normalize_course)
        placement_part['specialization_group'] = placement_df.get('branch', '').apply(normalize_course)
        placement_part['target'] = pd.to_numeric(placement_df.get('placed'), errors='coerce').fillna(0).clip(0, 1).astype(int)

        out = pd.concat([out, placement_part], ignore_index=True)

    return out.dropna()


def _read_onet_text_table(filename: str, usecols: list[str] | None = None) -> pd.DataFrame:
    path = ONET_TEXT_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep='\t', low_memory=False, usecols=usecols)


def _onet_group_top_strings(df: pd.DataFrame, *, code_col: str, value_col: str, k: int) -> dict[str, list[str]]:
    if df.empty or code_col not in df.columns or value_col not in df.columns:
        return {}
    trimmed = df[[code_col, value_col]].dropna()
    trimmed[value_col] = trimmed[value_col].astype(str).str.strip()
    trimmed = trimmed[trimmed[value_col].astype(str).str.len() > 0]
    grouped: dict[str, list[str]] = {}
    for code, group in trimmed.groupby(code_col):
        values = group[value_col].astype(str).tolist()
        seen = set()
        unique = []
        for item in values:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
            if len(unique) >= k:
                break
        grouped[str(code)] = unique
    return grouped


def build_onet_career_samples(max_per_path: int = 2200) -> pd.DataFrame:
    """
    Build labeled text samples from O*NET 29.0 text tables.
    These samples make the career comparison model less dependent on noisy job-posting text.
    """
    occupations = _read_onet_text_table(
        'Occupation Data.txt',
        usecols=['O*NET-SOC Code', 'Title', 'Description'],
    )
    if occupations.empty:
        return pd.DataFrame(columns=['title', 'skills_text', 'description', 'experience_years', 'salary', 'skills_count', 'certifications', 'text', 'path'])

    alt_titles = _read_onet_text_table(
        'Alternate Titles.txt',
        usecols=['O*NET-SOC Code', 'Alternate Title'],
    )
    skills = _read_onet_text_table(
        'Skills.txt',
        usecols=['O*NET-SOC Code', 'Element Name', 'Scale ID', 'Data Value'],
    )
    tech_skills = _read_onet_text_table(
        'Technology Skills.txt',
        usecols=['O*NET-SOC Code', 'Example'],
    )
    tools = _read_onet_text_table(
        'Tools Used.txt',
        usecols=['O*NET-SOC Code', 'Example'],
    )

    alt_map = _onet_group_top_strings(alt_titles, code_col='O*NET-SOC Code', value_col='Alternate Title', k=5)

    skill_map: dict[str, list[str]] = {}
    if not skills.empty:
        skills = skills.copy()
        skills['Scale ID'] = skills['Scale ID'].fillna('').astype(str)
        skills = skills[skills['Scale ID'].str.upper().eq('IM')].copy()
        skills['Data Value'] = pd.to_numeric(skills['Data Value'], errors='coerce').fillna(0.0)
        skills = skills.sort_values(['O*NET-SOC Code', 'Data Value'], ascending=[True, False])
        for code, group in skills.groupby('O*NET-SOC Code'):
            names = group['Element Name'].astype(str).tolist()
            seen = set()
            top = []
            for name in names:
                key = name.lower().strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                top.append(name.strip())
                if len(top) >= 10:
                    break
            skill_map[str(code)] = top

    tech_map = _onet_group_top_strings(tech_skills, code_col='O*NET-SOC Code', value_col='Example', k=10)
    tool_map = _onet_group_top_strings(tools, code_col='O*NET-SOC Code', value_col='Example', k=8)

    rows = []
    for record in occupations.to_dict(orient='records'):
        code = str(record.get('O*NET-SOC Code') or '').strip()
        title = str(record.get('Title') or '').strip()
        description = str(record.get('Description') or '').strip()
        if not code or not title:
            continue

        alt = " ".join(alt_map.get(code, []))
        skills_text = " ".join(skill_map.get(code, []))
        tech_text = " ".join(tech_map.get(code, []))
        tool_text = " ".join(tool_map.get(code, []))

        combined_text = " ".join(part for part in [title, alt, skills_text, tech_text, tool_text, description] if part).strip()
        path = classify_career_path(f"{title} {alt} {skills_text} {tech_text}")
        if path is None:
            # O*NET has many occupations outside our path set; skip unlabeled rows.
            continue

        rows.append({
            'title': title,
            'skills_text': " ".join(part for part in [skills_text, tech_text, tool_text] if part),
            'description': description,
            'experience_years': 2.0,
            'salary': 0.0,
            'skills_count': max(len(split_items(skills_text)), len(extract_skill_hits(combined_text))),
            'certifications': 0.0,
            'text': combined_text,
            'path': path,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = (
        df.groupby('path', group_keys=False)
        .apply(lambda frame: frame.sample(n=min(len(frame), max_per_path), random_state=42))
        .reset_index(drop=True)
    )
    return df


def build_finance_dataset():
    credit_df = pd.read_csv(DATASETS_DIR / 'finance' / 'credit_risk_dataset.csv')
    personal_df = pd.read_csv(DATASETS_DIR / 'finance' / 'synthetic_personal_finance_dataset.csv')

    grade_map = {'A': 790, 'B': 730, 'C': 680, 'D': 630, 'E': 580, 'F': 530, 'G': 480}
    credit_part = pd.DataFrame()
    credit_part['income'] = credit_df['person_income'].clip(lower=1)
    credit_part['loan'] = credit_df['loan_amnt'].clip(lower=0)
    credit_part['credit_score'] = (
        credit_df['loan_grade'].map(grade_map).fillna(650)
        - credit_df['cb_person_default_on_file'].eq('Y').astype(int) * 40
        + credit_df['cb_person_cred_hist_length'].fillna(5) * 3
        - credit_df['loan_int_rate'].fillna(10) * 2
    ).clip(300, 850)
    credit_part['loan_to_income'] = (credit_part['loan'] / credit_part['income']).clip(0, 5)
    credit_part['monthly_income'] = credit_part['income'] / 12.0
    credit_part['disposable_income_estimate'] = (credit_part['income'] - credit_part['loan']).clip(lower=0)
    credit_part['credit_buffer'] = (credit_part['credit_score'] - 650).clip(lower=0)
    credit_part['target'] = (credit_df['loan_status'] == 0).astype(int)

    personal_part = pd.DataFrame()
    personal_part['income'] = personal_df['monthly_income_usd'].clip(lower=1) * 12
    personal_part['loan'] = personal_df['loan_amount_usd'].fillna(0).clip(lower=0)
    personal_part['credit_score'] = personal_df['credit_score'].clip(300, 850)
    personal_part['loan_to_income'] = (personal_part['loan'] / personal_part['income']).clip(0, 5)
    personal_part['monthly_income'] = personal_part['income'] / 12.0
    personal_part['disposable_income_estimate'] = (personal_part['income'] - personal_part['loan']).clip(lower=0)
    personal_part['credit_buffer'] = (personal_part['credit_score'] - 650).clip(lower=0)
    personal_part['target'] = (
        (personal_df['debt_to_income_ratio'].fillna(0) < 0.45)
        & (personal_df['credit_score'].fillna(0) >= 640)
        & (personal_df['savings_to_income_ratio'].fillna(0) >= 0.4)
    ).astype(int)

    return pd.concat([credit_part, personal_part], ignore_index=True).dropna()


def build_startup_dataset():
    """Honest early-stage-aware dataset (fixed Sep 2026).

    - Labels come ONLY from real outcomes (IPO/Acquisition = 1). The old
      quantile-jugaad (success_quality/funding_quality) inflated accuracy to
      ~83% and taught the model that only huge later-stage companies succeed.
    - funding_part (startup_funding.csv) is excluded: it hardcoded
      team_size=8 / experience=5.0 for every row, i.e. 3k rows of pure noise
      that destroyed any real team/experience signal.
    - Early-stage underrepresentation is handled at inference via a disclosed
      empirical calibration floor (see startup_service), not by faking labels.
    """
    success_df = pd.read_csv(DATASETS_DIR / 'startup' / 'startup_success_dataset.csv')

    success_part = pd.DataFrame()
    success_part['funding'] = (success_df['funding_rounds'].fillna(0).clip(lower=0) * 1_000_000).astype(float)
    success_part['team_size'] = success_df['team_size'].fillna(success_df['team_size'].median()).clip(lower=1)
    success_part['market'] = success_df['sector'].apply(map_market)
    success_part['experience'] = success_df['founder_experience_years'].fillna(0).clip(lower=0)
    success_part['funding_per_team'] = (success_part['funding'] / success_part['team_size']).clip(0, 100_000_000)
    success_part['runway_score'] = (success_part['funding'] / 300000.0).clip(0, 4)
    success_part['experience_per_team_member'] = (success_part['experience'] / success_part['team_size']).clip(0, 10)
    success_part['capital_efficiency'] = (success_part['funding_per_team'] / 100000.0).clip(0, 1000)
    success_part['target'] = success_df['outcome'].isin(['IPO', 'Acquisition']).astype(int)

    combined = success_part.copy()
    combined['funding'] = combined['funding'].fillna(combined['funding'].median())
    combined['funding_per_team'] = combined['funding_per_team'].fillna(combined['funding_per_team'].median())
    return combined.dropna()


def build_policy_dataset():
    schemes_df = pd.read_csv(DATASETS_DIR / 'policy' / 'Indian Government Schemes.csv')

    scheme_part = pd.DataFrame()
    sector_source = (
        schemes_df['schemeCategory'].fillna('')
        + ' '
        + schemes_df['tags'].fillna('')
        + ' '
        + schemes_df['details'].fillna('')
    )
    scheme_part['sector'] = sector_source.apply(map_sector)
    scheme_part['budget'] = schemes_df['benefits'].apply(parse_rupee_amount).fillna(250000).clip(lower=10000)
    level = schemes_df['level'].fillna('State').astype(str).str.lower()
    population_map = {'central': 50000000, 'state': 7000000, 'union territory': 1000000}
    scheme_part['population'] = level.map(population_map).fillna(3000000)
    scheme_part['per_capita_budget'] = (scheme_part['budget'] / scheme_part['population']).clip(lower=0)
    scheme_part['budget_log'] = np.log10(np.maximum(scheme_part['budget'], 1))
    scheme_part['population_log'] = np.log10(np.maximum(scheme_part['population'], 1))
    scheme_part['coverage_pressure'] = scheme_part['population'] / np.maximum(scheme_part['budget'], 1)
    text_score = (
        schemes_df['eligibility'].fillna('').str.len()
        + schemes_df['application'].fillna('').str.len()
        + schemes_df['documents'].fillna('').str.len()
        + schemes_df['benefits'].fillna('').str.len()
    )
    scheme_quality = (
        scheme_part['per_capita_budget'].clip(0, scheme_part['per_capita_budget'].quantile(0.95)) / max(scheme_part['per_capita_budget'].quantile(0.95), 1)
        + scheme_part['budget_log'] / max(scheme_part['budget_log'].max(), 1)
        + level.map({'central': 0.18, 'state': 0.12, 'union territory': 0.08}).fillna(0.06)
        + scheme_part['sector'].map({'healthcare': 0.10, 'education': 0.09, 'infrastructure': 0.07}).fillna(0.05)
        + (text_score / max(text_score.quantile(0.95), 1)) * 0.12
    )
    scheme_part['target'] = (scheme_quality >= scheme_quality.quantile(0.52)).astype(int)

    historical_df = read_excel_flexible(DATASETS_DIR / 'policy' / 'India 20 year dataset.xlsx')
    historical_rows = []
    if not historical_df.empty and 'Year' in historical_df.columns:
        for column in historical_df.columns:
            historical_df[column] = pd.to_numeric(historical_df[column], errors='coerce')
        historical_df = historical_df.dropna(subset=['Year']).sort_values('Year')
        estimated_population = np.linspace(1080000000, 1400000000, len(historical_df))
        infra_index = pd.to_numeric(historical_df['Roads'], errors='coerce') + pd.to_numeric(historical_df['Houses'], errors='coerce') * 1000 + pd.to_numeric(historical_df['Water supply'], errors='coerce')
        health_index = pd.to_numeric(historical_df['JSY'], errors='coerce') * 1000 - pd.to_numeric(historical_df['IMR'], errors='coerce') * 10000 - pd.to_numeric(historical_df['MMR'], errors='coerce') * 2000
        for idx, (_, row) in enumerate(historical_df.iterrows()):
            pop_value = float(estimated_population[idx])
            jsy = safe_float(row.get('JSY'), 0)
            roads = safe_float(row.get('Roads'), 0)
            water = safe_float(row.get('Water supply'), 0)
            health_budget = max(10000.0, jsy * 1_000_000)
            health_score = (
                min(jsy / max(historical_df['JSY'].max(), 1), 1.0) * 0.45
                + max(0.0, 1.0 - (safe_float(row.get('IMR'), 0) / max(historical_df['IMR'].max(), 1))) * 0.30
                + max(0.0, 1.0 - (safe_float(row.get('MMR'), 0) / max(historical_df['MMR'].max(), 1))) * 0.25
            )
            historical_rows.append({
                'sector': 'healthcare',
                'budget': health_budget,
                'population': pop_value,
                'per_capita_budget': health_budget / pop_value,
                'budget_log': math.log10(health_budget),
                'population_log': math.log10(pop_value),
                'coverage_pressure': pop_value / health_budget,
                'target': int(health_score >= 0.58),
            })
            infra_budget = max(10000.0, roads * 1000 + water * 100)
            infra_score = (
                min(roads / max(historical_df['Roads'].max(), 1), 1.0) * 0.44
                + min(water / max(historical_df['Water supply'].max(), 1), 1.0) * 0.28
                + min(safe_float(row.get('Houses'), 0) / max(historical_df['Houses'].max(), 1), 1.0) * 0.28
            )
            historical_rows.append({
                'sector': 'infrastructure',
                'budget': infra_budget,
                'population': pop_value,
                'per_capita_budget': infra_budget / pop_value,
                'budget_log': math.log10(infra_budget),
                'population_log': math.log10(pop_value),
                'coverage_pressure': pop_value / infra_budget,
                'target': int(infra_score >= 0.58),
            })

    history_part = pd.DataFrame(historical_rows)
    combined = pd.concat([scheme_part, history_part], ignore_index=True)
    combined['budget'] = combined['budget'].fillna(combined['budget'].median()).clip(lower=10000)
    combined['population'] = combined['population'].fillna(combined['population'].median()).clip(lower=1000)
    combined['per_capita_budget'] = combined['per_capita_budget'].fillna(combined['per_capita_budget'].median()).clip(lower=0)
    return combined.dropna()


def build_career_path_bundle():
    postings_df = read_excel_flexible(DATASETS_DIR / 'career' / 'indian-job-market-dataset-2025.xlsx')
    salary_df = pd.read_csv(DATASETS_DIR / 'career' / 'job_salary_prediction_dataset.csv')
    if len(postings_df) > 8000:
        postings_df = postings_df.sample(n=8000, random_state=42)
    if len(salary_df) > 12000:
        salary_df = salary_df.sample(n=12000, random_state=42)

    posting_part = pd.DataFrame()
    posting_part['title'] = postings_df.get('title', '').fillna('')
    posting_part['skills_text'] = postings_df.get('tagsAndSkills', '').fillna('')
    posting_part['description'] = postings_df.get('jobDescription', '').fillna('')
    posting_part['experience_years'] = (
        pd.to_numeric(postings_df.get('minimumExperience'), errors='coerce').fillna(np.nan)
        + pd.to_numeric(postings_df.get('maximumExperience'), errors='coerce').fillna(np.nan)
    ) / 2
    posting_part['experience_years'] = posting_part['experience_years'].fillna(postings_df.get('experience', '').apply(parse_experience_range) if 'experience' in postings_df else np.nan).fillna(2)
    posting_part['salary'] = (
        pd.to_numeric(postings_df.get('minimumSalary'), errors='coerce').fillna(np.nan)
        + pd.to_numeric(postings_df.get('maximumSalary'), errors='coerce').fillna(np.nan)
    ) / 2
    posting_part['salary'] = posting_part['salary'].fillna(0)
    posting_part['skills_count'] = posting_part['skills_text'].apply(lambda value: len(split_items(value)))
    posting_part['certifications'] = 0
    posting_part['text'] = (
        posting_part['title'].astype(str)
        + ' '
        + posting_part['skills_text'].astype(str)
        + ' '
        + posting_part['description'].astype(str)
    )
    posting_labels = (posting_part['title'].astype(str) + ' ' + posting_part['skills_text'].astype(str)).apply(classify_career_path)
    posting_part['path'] = posting_labels

    salary_part = pd.DataFrame()
    salary_part['title'] = salary_df['job_title'].fillna('')
    salary_part['skills_text'] = salary_part['title'].astype(str)
    salary_part['description'] = salary_df['industry'].fillna('') + ' ' + salary_df['location'].fillna('') + ' ' + salary_df['remote_work'].fillna('')
    salary_part['experience_years'] = pd.to_numeric(salary_df['experience_years'], errors='coerce').fillna(0)
    salary_part['salary'] = pd.to_numeric(salary_df['salary'], errors='coerce').fillna(0)
    salary_part['skills_count'] = pd.to_numeric(salary_df['skills_count'], errors='coerce').fillna(0)
    salary_part['certifications'] = pd.to_numeric(salary_df['certifications'], errors='coerce').fillna(0)
    salary_part['text'] = (
        salary_part['title'].astype(str)
        + ' '
        + salary_df['industry'].fillna('').astype(str)
        + ' '
        + salary_df['education_level'].fillna('').astype(str)
        + ' '
        + salary_df['remote_work'].fillna('').astype(str)
    )
    salary_labels = salary_part['title'].apply(classify_career_path)
    salary_part['path'] = salary_labels

    onet_part = build_onet_career_samples()
    combined = pd.concat([posting_part, salary_part, onet_part], ignore_index=True)
    combined = combined[combined['path'].notna()].copy()
    combined = (
        combined.groupby('path', group_keys=False)
        .apply(lambda frame: frame.sample(n=min(len(frame), 2500), random_state=42))
        .reset_index(drop=True)
    )
    combined['text'] = combined['text'].astype(str)
    combined['experience_years'] = combined['experience_years'].fillna(combined['experience_years'].median()).clip(lower=0)
    combined['salary'] = combined['salary'].fillna(combined['salary'].median()).clip(lower=0)
    combined['skills_count'] = combined['skills_count'].fillna(combined['skills_count'].median()).clip(lower=0)
    combined['certifications'] = combined['certifications'].fillna(0).clip(lower=0)

    X = combined[['text', 'experience_years', 'skills_count', 'certifications', 'salary']]
    y = combined['path']

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    pipeline = Pipeline([
        ('preprocessor', ColumnTransformer([
            ('text', TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=2500), 'text'),
            ('num', Pipeline([
                ('imputer', SimpleImputer(strategy='median')),
                ('scaler', StandardScaler()),
            ]), ['experience_years', 'skills_count', 'certifications', 'salary']),
        ])),
        ('model', LogisticRegression(
            max_iter=2500,
            class_weight='balanced',
            solver='lbfgs',
            random_state=42,
        )),
    ])

    pipeline.fit(X_train, y_train)
    predictions = pipeline.predict(X_test)
    probabilities = pipeline.predict_proba(X_test)
    metrics = {
        'accuracy': round(float(accuracy_score(y_test, predictions)), 4),
        'f1_macro': round(float(f1_score(y_test, predictions, average='macro', zero_division=0)), 4),
    }

    pipeline.fit(X, y)
    class_order = pipeline.named_steps['model'].classes_.tolist()
    text_vectorizer = pipeline.named_steps['preprocessor'].named_transformers_['text']
    vocabulary = np.asarray(text_vectorizer.get_feature_names_out())

    path_profiles = {}
    global_skill_counter = Counter()
    for text in combined['text'].astype(str).tolist():
        global_skill_counter.update(extract_skill_hits(text))

    for class_index, path_name in enumerate(class_order):
        subset = combined[combined['path'] == path_name]
        model = pipeline.named_steps['model']
        if hasattr(model, 'coef_'):
            text_signal = model.coef_[class_index][:len(vocabulary)]
        else:
            # Tree models expose global feature importance rather than per-class coefficients.
            text_signal = model.feature_importances_[:len(vocabulary)]
        top_indices = np.argsort(text_signal)[-12:][::-1]
        top_terms = [term.replace('_', ' ') for term in vocabulary[top_indices] if term not in STOPWORDS][:8]

        skill_counter = Counter()
        for text in subset['text'].astype(str).tolist():
            skill_counter.update(extract_skill_hits(text))
        lifted_skills = []
        subset_size = max(len(subset), 1)
        total_size = max(len(combined), 1)
        for skill, count in skill_counter.items():
            path_rate = count / subset_size
            global_rate = global_skill_counter.get(skill, 1) / total_size
            lift = path_rate / max(global_rate, 1e-6)
            lifted_skills.append((skill, lift, count))
        lifted_skills.sort(key=lambda item: (item[1], item[2]), reverse=True)
        top_skills = [skill for skill, _, _ in lifted_skills[:8]]

        path_profiles[path_name] = {
            'display_name': PATH_DISPLAY_NAMES.get(path_name, path_name.replace('_', ' ').title()),
            'demand_count': int(len(subset)),
            'salary_median': round(float(subset['salary'].median()), 2),
            'experience_median': round(float(subset['experience_years'].median()), 2),
            'top_terms': top_terms,
            'top_skills': top_skills,
            'market_score': round(float(len(subset) / max(len(combined), 1)), 4),
        }

    return {
        'pipeline': pipeline,
        'metrics': metrics,
        'class_order': class_order,
        'path_profiles': path_profiles,
        'label_audit': build_career_label_audit(posting_labels, salary_labels, class_order),
    }


def save_bundle(domain, bundle):
    joblib.dump(bundle, MODELS_DIR / f'{domain}_model.joblib')


def main():
    summaries = {}

    career_df = build_career_dataset()
    career_bundle = train_tree_bundle(
        'career',
        career_df,
        ['cgpa', 'skills_count', 'projects_count', 'certifications_count', 'internship_count', 'experience_years', 'portfolio_strength', 'skill_project_ratio'],
        ['interest', 'course_group', 'specialization_group'],
        {
            'cgpa': 'CGPA',
            'skills_count': 'Skill count',
            'projects_count': 'Project count',
            'certifications_count': 'Certification count',
            'internship_count': 'Internship count',
            'experience_years': 'Experience years',
            'portfolio_strength': 'Portfolio strength',
            'skill_project_ratio': 'Skill-to-project ratio',
            'interest': 'Interest area',
            'course_group': 'Degree group',
            'specialization_group': 'Specialization group',
        },
    )
    career_bundle['comparison'] = build_career_path_bundle()
    save_bundle('career', career_bundle)
    summaries['career'] = career_bundle['metrics']
    summaries['career_path'] = career_bundle['comparison']['metrics']

    finance_df = build_finance_dataset()
    finance_bundle = train_tree_bundle(
        'finance',
        finance_df,
        ['income', 'loan', 'credit_score', 'loan_to_income', 'monthly_income', 'disposable_income_estimate', 'credit_buffer'],
        [],
        {
            'income': 'Income',
            'loan': 'Loan amount',
            'credit_score': 'Credit score',
            'loan_to_income': 'Loan-to-income ratio',
            'monthly_income': 'Monthly income',
            'disposable_income_estimate': 'Disposable income estimate',
            'credit_buffer': 'Credit buffer',
        },
    )
    save_bundle('finance', finance_bundle)
    summaries['finance'] = finance_bundle['metrics']

    startup_df = build_startup_dataset()
    startup_bundle = train_tree_bundle(
        'startup',
        startup_df,
        ['funding', 'team_size', 'experience', 'funding_per_team', 'runway_score', 'experience_per_team_member', 'capital_efficiency'],
        ['market'],
        {
            'funding': 'Funding',
            'team_size': 'Team size',
            'experience': 'Founder experience',
            'funding_per_team': 'Funding per team member',
            'runway_score': 'Runway score',
            'experience_per_team_member': 'Experience per team member',
            'capital_efficiency': 'Capital efficiency',
            'market': 'Market type',
        },
    )
    save_bundle('startup', startup_bundle)
    summaries['startup'] = startup_bundle['metrics']

    policy_df = build_policy_dataset()
    policy_bundle = train_tree_bundle(
        'policy',
        policy_df,
        ['budget', 'population', 'per_capita_budget', 'budget_log', 'population_log', 'coverage_pressure'],
        ['sector'],
        {
            'budget': 'Budget',
            'population': 'Population',
            'per_capita_budget': 'Per-capita budget',
            'budget_log': 'Budget log scale',
            'population_log': 'Population log scale',
            'coverage_pressure': 'Coverage pressure',
            'sector': 'Sector',
        },
    )
    save_bundle('policy', policy_bundle)
    summaries['policy'] = policy_bundle['metrics']

    summary_path = MODELS_DIR / 'training_summary.json'
    summary_path.write_text(json.dumps(summaries, indent=2), encoding='utf-8')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
