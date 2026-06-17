import json
import re
import difflib

with open('E:/workspace/ddl/data/venue_dict.json', encoding='utf-8') as f:
    v_dict = json.load(f)

test_venues = [
    'CVPR',
    'CVPR 2023',
    'IEEE/CVF Conference on Computer Vision and Pattern Recognition',
    'Computer Vision and Pattern Recognition',
    'CHI',
    'CHI Conference on Human Factors in Computing Systems',
    'ACM Conference on Human Factors in Computing Systems',
    'Human Factors in Computing Systems',
    'Pattern Recognition'
]

for ai_venue in test_venues:
    matched = None
    ai_venue_clean = ai_venue.lower()
    words = set(re.findall(r'\b[A-Za-z]+\b', ai_venue))
    
    for k, v in v_dict.items():
        if k in words and k.upper() == k and len(k) > 1:
            matched = v
            break
            
    if not matched:
        best_match = None
        best_score = 0
        best_k = None
        for k, v in v_dict.items():
            k_lower = k.lower()
            score = difflib.SequenceMatcher(None, ai_venue_clean, k_lower).ratio()
            if k_lower in ai_venue_clean:
                score = max(score, len(k_lower) / max(len(ai_venue_clean), 1))
            elif ai_venue_clean in k_lower:
                score = max(score, len(ai_venue_clean) / max(len(k_lower), 1))
                
            if score > best_score:
                best_score = score
                best_match = v
                best_k = k
                
        if best_score > 0.55:
            matched = best_match
            print(f'"{ai_venue}" matched fuzzy -> {best_k} (score {best_score:.2f}) [CCF: {matched.get("ccf")}]')
        else:
            print(f'"{ai_venue}" NO MATCH (best {best_k} score {best_score:.2f})')
    else:
        print(f'"{ai_venue}" matched exact acronym [CCF: {matched.get("ccf")}]')
