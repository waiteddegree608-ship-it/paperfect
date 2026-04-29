import os
import shutil
import glob

def migrate():
    base_dir = "E:\\workspace\\ddl"
    data_dir = os.path.join(base_dir, "data")
    
    # Create target directories
    for category in ["papers", "textbooks"]:
        for sub in ["raw", "parsed", "translated", "marked", "images", "pptx", "cache"]:
            os.makedirs(os.path.join(data_dir, category, sub), exist_ok=True)
            
    # Map old directories
    old_papers = os.path.join(base_dir, "papers")
    old_imports = os.path.join(base_dir, "imports")
    
    def process_category(old_dir, new_cat):
        if not os.path.exists(old_dir):
            return
            
        for item in os.listdir(old_dir):
            item_path = os.path.join(old_dir, item)
            
            if os.path.isfile(item_path):
                if item.endswith("_translated.pdf"):
                    shutil.move(item_path, os.path.join(data_dir, new_cat, "translated", item))
                elif item.endswith("_annotated.pdf"):
                    shutil.move(item_path, os.path.join(data_dir, new_cat, "marked", item))
                elif item.endswith(".pdf"):
                    shutil.move(item_path, os.path.join(data_dir, new_cat, "raw", item))
                    
            elif os.path.isdir(item_path):
                # It's a folder for a specific document
                doc_name = item
                for subitem in os.listdir(item_path):
                    subitem_path = os.path.join(item_path, subitem)
                    if subitem.endswith("_KnowledgeBase.md") or subitem.startswith("输出结果_"):
                        shutil.move(subitem_path, os.path.join(data_dir, new_cat, "parsed", subitem))
                    elif subitem.endswith("_Full_Presentation.pptx"):
                        shutil.move(subitem_path, os.path.join(data_dir, new_cat, "pptx", subitem))
                    elif subitem == "figures" or subitem == "temp_assets":
                        # move contents to images folder, prefixing with doc_name
                        if os.path.isdir(subitem_path):
                            for img in os.listdir(subitem_path):
                                src_img = os.path.join(subitem_path, img)
                                if os.path.isfile(src_img):
                                    shutil.move(src_img, os.path.join(data_dir, new_cat, "images", f"{doc_name}_{img}"))
                    elif subitem == "markdown_parts":
                        if os.path.isdir(subitem_path):
                            for md in os.listdir(subitem_path):
                                src_md = os.path.join(subitem_path, md)
                                if os.path.isfile(src_md):
                                    shutil.move(src_md, os.path.join(data_dir, new_cat, "cache", f"{doc_name}_{md}"))
                    elif subitem.endswith("_annotated.pdf"):
                        shutil.move(subitem_path, os.path.join(data_dir, new_cat, "marked", subitem))
                        
                # Remove empty dir
                try:
                    os.rmdir(item_path)
                except OSError:
                    pass

    process_category(old_papers, "papers")
    process_category(old_imports, "textbooks")
    
    # Try to remove old base dirs if empty
    try: os.rmdir(old_papers)
    except OSError: pass
    try: os.rmdir(old_imports)
    except OSError: pass

if __name__ == "__main__":
    migrate()
    print("Migration completed.")
