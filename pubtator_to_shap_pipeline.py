import re
import json
import argparse
import pandas as pd
import numpy as np
from collections import defaultdict
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
import shap
import os

# Import NetMedEx parsers
try:
    from netmedex.biocjson_parser import biocjson_to_pubtator
except ImportError:
    print("Warning: netmedex package not found in path. Using default text parser only.")
    biocjson_to_pubtator = None

# =========================
# CONFIG & CONSTANTS
# =========================
VALID_TYPES = {
    "Gene",
    "Disease",
    "DNAMutation",
    "ProteinMutation",
    "SNP",
    "Chemical"
}

# Tumor dictionary (can be extended)
TUMOR_MAP = {
    "medulloblastoma": "medulloblastoma",
    "germinoma": "germinoma",
    "ependymoma": "ependymoma",
    "glioma": "glioma",
    "diffuse midline glioma": "dmg",
    "atypical teratoid rhabdoid tumor": "atrt"
}

# =========================
# STEP 1: PARSE INPUT
# =========================

def parse_input(file_path):
    pmid_entities = defaultdict(set)
    pmid_diseases = defaultdict(set)

    if file_path.endswith(".json"):
        print(f"Parsing BioC-JSON: {file_path}")
        if biocjson_to_pubtator is None:
            raise ImportError("biocjson_to_pubtator is required for JSON parsing but failed to import.")
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        
        articles = biocjson_to_pubtator(data)
        print(f"Loaded {len(articles)} articles from JSON.")
        
        for article in articles:
            pmid = article.pmid
            for ann in article.annotations:
                mention = ann.name.lower()
                etype = ann.type
                
                if etype not in VALID_TYPES:
                    continue
                
                feature = f"{etype}:{mention}"
                pmid_entities[pmid].add(feature)
                
                if etype == "Disease":
                    pmid_diseases[pmid].add(mention)
    else:
        print(f"Parsing Tab-separated PubTator: {file_path}")
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                if "\t" not in line:
                    continue

                parts = line.strip().split("\t")
                if len(parts) < 5:
                    continue

                pmid = parts[0]
                mention = parts[3].lower()
                etype = parts[4]

                if etype not in VALID_TYPES:
                    continue

                feature = f"{etype}:{mention}"
                pmid_entities[pmid].add(feature)

                if etype == "Disease":
                    pmid_diseases[pmid].add(mention)

    return pmid_entities, pmid_diseases

# =========================
# STEP 2: BUILD LABEL
# =========================

def assign_label(diseases):
    for d in diseases:
        for key in TUMOR_MAP:
            if key in d:
                return TUMOR_MAP[key]
    return None

# =========================
# STEP 3: BUILD MATRIX
# =========================

def build_matrix(pmid_entities, pmid_diseases):
    rows = []

    for pmid in pmid_entities:
        label = assign_label(pmid_diseases[pmid])
        if label is None:
            continue

        row = {"pmid": pmid, "label": label}
        for feat in pmid_entities[pmid]:
            row[feat] = 1

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).fillna(0)
    return df

# =========================
# STEP 4: TRAIN MODEL + SHAP
# =========================

def compute_shap(df):
    X = df.drop(columns=["pmid", "label"])
    y = df["label"]

    # Sanitize feature names for XGBoost compatibility (no [, ], <, or >)
    # Aggressively replace all non-alphanumeric (except underscores) with underscores
    new_cols = [re.sub(r"[^a-zA-Z0-9_]", "_", str(col)) for col in X.columns]
    
    # Handle duplicates that might arise from sanitization
    final_cols = []
    seen = set()
    for col in new_cols:
        candidate = col
        suffix = 1
        while candidate in seen:
            candidate = f"{col}_{suffix}"
            suffix += 1
        final_cols.append(candidate)
        seen.add(candidate)
    X.columns = final_cols

    # encode label
    labels = y.astype("category")
    y_encoded = labels.cat.codes
    class_names = labels.cat.categories

    print(f"Training on {len(class_names)} classes: {list(class_names)}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
    )

    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss"
    )

    model.fit(X_train, y_train)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test)

    # For multiclass, shap_values is a list of arrays (one per class)
    # We take the mean absolute SHAP across all classes as a general importance measure
    if isinstance(shap_values, list):
        # shap_values[class_i] shape: (n_samples, n_features)
        shap_array = np.mean([np.abs(sv) for sv in shap_values], axis=0) # mean across classes
        mean_abs_shap = shap_array.mean(axis=0) # mean across samples
    else:
        # Binary case or older SHAP version
        mean_abs_shap = np.abs(shap_values).mean(axis=0)

    shap_df = pd.DataFrame({
        "node_id": X.columns,
        "shap_value": mean_abs_shap
    }).sort_values("shap_value", ascending=False)

    return shap_df

# =========================
# MAIN
# =========================

def main():
    parser = argparse.ArgumentParser(description="PubTator to SHAP Pipeline")
    parser.add_argument("--input", "-i", default="CNS_Tumors_Pediatric_BioC.json", help="Input file (.json or .txt)")
    parser.add_argument("--output-matrix", "-m", default="training_matrix.csv", help="Output matrix CSV")
    parser.add_argument("--output-shap", "-s", default="shap_scores.csv", help="Output SHAP scores CSV")
    
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file {args.input} not found.")
        return

    print(f"Step 1: Loading/Parsing {args.input}...")
    if args.input.endswith(".csv"):
        df = pd.read_csv(args.input)
        print(f"Loaded matrix from CSV. Shape: {df.shape}")
    else:
        pmid_entities, pmid_diseases = parse_input(args.input)
        print("Step 2: Building matrix...")
        df = build_matrix(pmid_entities, pmid_diseases)
        if not df.empty:
            df.to_csv(args.output_matrix, index=False)
            print(f"Matrix saved to {args.output_matrix}. Shape: {df.shape}")
    
    if df.empty:
        print("Error: No labeled data found. Check TUMOR_MAP and input file.")
        return

    print("Step 3: Training model and computing SHAP values...")
    shap_df = compute_shap(df)
    shap_df.to_csv(args.output_shap, index=False)

    print(f"Pipeline complete. SHAP scores saved to {args.output_shap}")
    print("\nTop 10 Most Important Features:")
    print(shap_df.head(10))


if __name__ == "__main__":
    main()
