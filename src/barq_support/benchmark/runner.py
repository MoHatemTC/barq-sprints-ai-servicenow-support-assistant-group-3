import json
import time
import argparse
from typing import List, Dict, Any

# Integration point for Qdrant Search Function
def mock_semantic_search(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    MOCKED FOR PR REVIEW: Returns representative test scores to validate the 
    Hit Rate and Abstention math until the live retrieval function is merged.
    """
    # Negative Control Mocks (Scores under 0.45)
    if "grinding" in query: return [{"article_id": "KB0010011", "score": 0.31}]
    if "monitor" in query: return [{"article_id": "KB0010032", "score": 0.25}]
    if "expense" in query: return [{"article_id": "KB0010014", "score": 0.18}]
    
    # Answerable Incident Mocks (Scores between 0.75 - 0.88)
    if "VPN" in query: return [{"article_id": "KB0010001", "score": 0.85}]
    if "Outlook" in query: return [{"article_id": "KB0010003", "score": 0.82}]
    if "shared drive" in query: return [{"article_id": "KB0010004", "score": 0.78}]
    if "Jobs queue" in query: return [{"article_id": "KB0010011", "score": 0.81}]
    if "locked out" in query: return [{"article_id": "KB0010014", "score": 0.76}]
    if "authenticator" in query: return [{"article_id": "KB0010015", "score": 0.79}]
    if "Windows update" in query: return [{"article_id": "KB0010012", "score": 0.84}]
    if "SAP" in query: return [{"article_id": "KB0010013", "score": 0.88}]
    if "5 GHz" in query: return [{"article_id": "KB0010017", "score": 0.77}]
    if "Order service" in query: return [{"article_id": "KB0010016", "score": 0.83}]
    if "OSPF" in query: return [{"article_id": "KB0010018", "score": 0.81}]
    if "latency" in query: return [{"article_id": "KB0010020", "score": 0.75}]
    
    return []

def calculate_optimal_threshold(valid_scores: List[float], negative_scores: List[float]) -> float:
    """
    Calculates the optimal similarity threshold to separate valid hits from noise.
    """
    if not valid_scores or not negative_scores:
        return 0.55 # Fallback to historical baseline if data is missing
        
    lowest_valid = min(valid_scores)
    highest_negative = max(negative_scores)
    
    print(f"\n--- Threshold Analysis ---")
    print(f"Lowest Valid Score:     {lowest_valid:.3f}")
    print(f"Highest Negative Score: {highest_negative:.3f}")
    
    if lowest_valid > highest_negative:
        # Perfect separation. Find the midpoint.
        optimal = (lowest_valid + highest_negative) / 2
        print(f"Status: Perfect separation achieved.")
    else:
        # Overlap exists. Optimize for Abstention to prevent hallucinations.
        optimal = highest_negative + 0.01
        print(f"Status: Overlap detected. Prioritizing strict Abstention.")
        
    print(f"Recommended Threshold:  {optimal:.3f}\n")
    return optimal

# Evaluation Logic
def run_benchmark(dataset_path: str, threshold: float = 0.55, top_k: int = 3):
    print(f"--- Starting Retrieval Benchmark (Threshold: {threshold}, Top-K: {top_k}) ---\n")
    
    try:
        with open(dataset_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find dataset at {dataset_path}")
        return

    answerable = data.get("answerable_incidents", [])
    negative_controls = data.get("negative_controls", [])

    hits = 0
    mrr_sum = 0.0
    correct_refusals = 0
    total_latency = 0.0
    
    # New lists to track scores for the calculator
    valid_scores_tracked = []
    negative_scores_tracked = []

    print(">>> Evaluating Answerable Incidents")
    for inc in answerable:
        start_time = time.time()
        
        # DEFENSIVE EXCEPTION HANDLING ADDED HERE
        try:
            results = mock_semantic_search(inc["query"], top_k=top_k)
        except Exception as e:
            print(f"  [ERROR] Retrieval failed for {inc['id']}: {e}")
            results = []
            
        total_latency += (time.time() - start_time)
        
        results = sorted(results, key=lambda x: x.get("score", 0.0), reverse=True)
        expected = inc["expected_article"]
        
        # Track the score of the EXPECTED article if it was found
        found_score = next((r["score"] for r in results if r.get("article_id") == expected), None)
        if found_score is not None:
            valid_scores_tracked.append(found_score)
            
        # Standard threshold check
        valid_results = [res for res in results if res.get("score", 0.0) >= threshold]
        
        retrieved_details = [f"{res.get('article_id')} ({res.get('score', 0.0):.2f})" for res in valid_results]
        retrieved_articles = [res.get("article_id") for res in valid_results]

        passed = expected in retrieved_articles
        if passed:
            hits += 1
            rank = retrieved_articles.index(expected) + 1
            mrr_sum += 1.0 / rank
            
        print(f"[{'PASS' if passed else 'FAIL'}] {inc['id']} | Expected: {expected} | Retrieved: {retrieved_details}")

    # Evaluate abstention
    print("\n>>> Evaluating Negative Controls (Refusals)")
    for inc in negative_controls:
        start_time = time.time()
        
        # DEFENSIVE EXCEPTION HANDLING ADDED HERE
        try:
            results = mock_semantic_search(inc["query"], top_k=top_k)
        except Exception as e:
            print(f"  [ERROR] Retrieval failed for {inc['id']}: {e}")
            results = []
            
        total_latency += (time.time() - start_time)
        
        results = sorted(results, key=lambda x: x.get("score", 0.0), reverse=True)
        
        highest_score = results[0].get("score", 0.0) if results else 0.0
        negative_scores_tracked.append(highest_score)
        
        # System passes if NO chunks clear the threshold
        passed = highest_score < threshold
        if passed:
            correct_refusals += 1
            
        print(f"[{'PASS' if passed else 'FAIL'}] {inc['id']} | Expected: Refusal | Highest Score Found: {highest_score:.2f}")

    # Run the auto-calculator before printing the final benchmark results
    calculate_optimal_threshold(valid_scores_tracked, negative_scores_tracked)

    # Aggregate Metrics & Reporting
    total_queries = len(answerable) + len(negative_controls)
    hit_rate = (hits / len(answerable)) * 100 if answerable else 0
    mrr = (mrr_sum / len(answerable)) if answerable else 0
    refusal_rate = (correct_refusals / len(negative_controls)) * 100 if negative_controls else 0
    avg_latency = (total_latency / total_queries) * 1000 if total_queries else 0

    print("="*45)
    print("BENCHMARK RESULTS")
    print("="*45)
    print(f"Total Answerable Tested: {len(answerable)}")
    print(f"Hit Rate (@{top_k}):         {hit_rate:.1f}% ({hits}/{len(answerable)})")
    print(f"Mean Reciprocal Rank:    {mrr:.3f}")
    print(f"Total Controls Tested:   {len(negative_controls)}")
    print(f"Refusal Correctness:     {refusal_rate:.1f}% ({correct_refusals}/{len(negative_controls)})")
    print(f"Avg Retrieval Latency:   {avg_latency:.2f} ms")
    print("="*45)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RAG Retrieval Benchmark")
    parser.add_argument("--dataset", type=str, default="Benchmark_Dataset.json", help="Path to the JSON benchmark dataset")
    parser.add_argument("--threshold", type=float, default=0.55, help="Similarity score threshold")
    parser.add_argument("--top_k", type=int, default=3, help="Number of chunks to retrieve")
    
    args = parser.parse_args()
    run_benchmark(args.dataset, threshold=args.threshold, top_k=args.top_k)