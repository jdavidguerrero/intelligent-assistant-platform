"""Musical Intelligence Evaluation Framework.

Systematic quality measurement for the RAG system across 6 music sub-domains.

Modules
-------
dataset         — 50 golden Q&A pairs with ground truth
runner          — batch query executor against the /ask endpoint
retrieval_metrics — Recall@K, Precision@K, MRR per sub-domain
judge           — LLM-as-judge scoring (accuracy, relevance, actionability)
report          — per-sub-domain breakdown and one-page quality report
regression      — baseline comparison, catches quality drops >5%
"""
