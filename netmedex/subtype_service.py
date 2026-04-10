import joblib
import json
import os
import re
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

MODEL_PATH = "/home/cylin/NetMedEx/brain_network/subtype_classifier_v1.joblib"
MECHANISMS_PATH = "/home/cylin/NetMedEx/brain_network/cluster_mechanisms_v1.json"
# The 160 biomarkers used during training
FEATURE_LIST = [
    'gene:myc', 'gene:tp53', 'gene:idh1', 'gene:braf', 'gene:ptch1', 'gene:gli1', 'gene:smo', 'gene:sufu',
    'gene:shh', 'gene:tert', 'gene:atrx', 'gene:mgmt', 'gene:nf1', 'gene:nf2', 'gene:tsc1', 'gene:tsc2',
    'gene:mtor', 'gene:pik3ca', 'gene:pten', 'gene:egfr', 'gene:h3f3a', 'gene:hist1h3b', 'gene:k27m',
    'gene:v600e', 'gene:kiaa1549', 'gene:ctnnb1', 'gene:ddx3x', 'gene:sncaip', 'gene:prkra', 'gene:tagn',
    'gene:mycn', 'gene:otx2', 'gene:gli2', 'gene:foxg1', 'gene:foxo1', 'gene:foxo3', 'gene:stat3',
    'chemical:cisplatin', 'chemical:vincristine', 'chemical:cyclophosphamide', 'chemical:etoposide',
    'chemical:carboplatin', 'chemical:temozolomide', 'chemical:bevacizumab', 'chemical:sirolimus',
    'chemical:everolimus', 'chemical:dabrafenib', 'chemical:trametinib', 'chemical:vismodegib',
    'chemical:sonidegib', 'chemical:irinotecan'
]
# Note: I'll use a larger subset or full 160 if needed, but these cover the major subtypes.
# For production, we'll load the full columns from the matrix.

class SubtypeService:
    def __init__(self):
        self.model = None
        self.mechanisms = {}
        self.feature_names = []
        self._load_resources()

    def _load_resources(self):
        try:
            if os.path.exists(MODEL_PATH):
                self.model = joblib.load(MODEL_PATH)
                # Recover feature names from the model if possible
                if hasattr(self.model, 'feature_names_in_'):
                    self.feature_names = list(self.model.feature_names_in_)
        except Exception as e:
            logger.error(f"Failed to load subtype model: {e}")

        try:
            if os.path.exists(MECHANISMS_PATH):
                with open(MECHANISMS_PATH, 'r') as f:
                    raw_data = json.load(f)
                    # Convert keys to int strings
                    self.mechanisms = {str(k): v for k, v in raw_data.items()}
        except Exception as e:
            logger.error(f"Failed to load mechanisms: {e}")

    def predict_subtype(self, text: str) -> dict:
        """Analyze text, extract biomarkers, and predict subtype."""
        if not self.model or not self.feature_names:
            return {"cluster": 0, "name": "General/Unknown", "confidence": 0.0}

        # 1. Feature Extraction (Simple Keyword Match)
        # We assume the feature names match the format 'gene:myc', etc.
        features = {}
        text_lower = text.lower()
        for feat in self.feature_names:
            # Strip prefix for keyword matching (gene:myc -> myc)
            keyword = feat.split(':')[-1] if ':' in feat else feat
            # Use regex boundaries for better matching
            if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
                features[feat] = 1
            else:
                features[feat] = 0
        
        # 2. Inference
        df_input = pd.DataFrame([features])[self.feature_names]
        probs = self.model.predict_proba(df_input)[0]
        cid = int(np.argmax(probs))
        confidence = float(probs[cid])

        # 3. Cleanup names
        diagnoses = {
            "0": "General/Glioma", "1": "MYC-MB", "2": "IDH-Glioma", "3": "TSC/mTOR",
            "4": "BRAF-mutant", "5": "SHH-MB", "6": "NF1-Glioma", "7": "MGMT/TMZ High-Grade"
        }
        
        # 4. Get Mechanism Context
        mech = self.mechanisms.get(str(cid), {})
        
        return {
            "cluster_id": cid,
            "name": diagnoses.get(str(cid), "Unknown"),
            "confidence": confidence,
            "top_hubs": [h['node'] for h in mech.get('hubs', [])[:3]],
            "top_chain": mech.get('top_chains', [None])[0]
        }

    def format_subtype_context(self, result: dict) -> str:
        """Format the prediction into a prompt-friendly context string."""
        if result['confidence'] < 0.1: return ""
        
        ctx = f"### DETECTED SUBTYPE: {result['name']} (Cluster {result['cluster_id']})\n"
        ctx += f"- Confidence: {result['confidence']:.1%}\n"
        if result['top_hubs']:
            ctx += f"- Hallmark Hubs: {', '.join(result['top_hubs'])}\n"
        
        if result['top_chain']:
            p = result['top_chain']['path']
            r = result['top_chain']['relations']
            ctx += f"- Discovered Circuit: {p[0]} --({r[0]})--> {p[1]} --({r[1]})--> {p[2]}\n"
        
        return ctx

subtype_service = SubtypeService()
