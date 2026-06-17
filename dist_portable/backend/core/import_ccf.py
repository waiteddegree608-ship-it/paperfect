import os
import sys
import json
import pdfplumber

def import_ccf():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pdf_path = os.path.join(base_dir, "第七版中国计算机学会推荐国际学术会议和期刊目录（正式版）.pdf")
    dict_path = os.path.join(base_dir, "data", "venue_dict.json")
    
    if not os.path.exists(pdf_path):
        print(f"Error: Could not find {pdf_path}")
        return

    print("Parsing CCF 7th Edition PDF...")
    pdf = pdfplumber.open(pdf_path)
    
    # Existing dict
    venue_dict = {}
    if os.path.exists(dict_path):
        with open(dict_path, "r", encoding="utf-8") as f:
            try:
                venue_dict = json.load(f)
            except Exception:
                pass

    table_resets = 0
    added_count = 0
    
    # State machine: 
    # 0=Journal A, 1=Journal B, 2=Journal C
    # 3=Conf A, 4=Conf B, 5=Conf C
    # Cycle repeats for each of the 10 categories.
    levels = ["A", "B", "C", "A", "B", "C"]

    for page in pdf.pages:
        tables = page.extract_tables({'text_x_tolerance': 2})
        for table in tables:
            for row in table:
                if len(row) > 2:
                    no_col = str(row[0]).strip()
                    if no_col == '1':
                        table_resets += 1
                        
                    # If we haven't seen the first table yet, ignore random rows
                    if table_resets == 0:
                        continue
                        
                    current_level = levels[(table_resets - 1) % 6]
                    
                    # Valid row has a number
                    if no_col.isdigit():
                        acronym = str(row[1]).strip().replace('\n', '')
                        full_name = str(row[2]).strip().replace('\n', ' ')
                        
                        # Fix up full names that got squeezed together (heuristically add spaces before capitals if possible? No, too risky. Just use it as is for partial matching)
                        
                        # Add acronym if it exists
                        if acronym and acronym != '-':
                            if acronym not in venue_dict:
                                venue_dict[acronym] = {"ccf": current_level, "jcr": "", "core": ""}
                                added_count += 1
                            else:
                                venue_dict[acronym]["ccf"] = current_level
                                
                        # Add full name
                        if full_name and len(full_name) > 5:
                            if full_name not in venue_dict:
                                venue_dict[full_name] = {"ccf": current_level, "jcr": "", "core": ""}
                                added_count += 1
                            else:
                                venue_dict[full_name]["ccf"] = current_level

    with open(dict_path, "w", encoding="utf-8") as f:
        json.dump(venue_dict, f, ensure_ascii=False, indent=4)
        
    print(f"Successfully processed PDF. Total table resets found: {table_resets} (Should be 60).")
    print(f"Added/Updated {added_count} venue entries in venue_dict.json")

if __name__ == "__main__":
    import_ccf()
