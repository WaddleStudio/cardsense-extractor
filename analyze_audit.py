import json
import glob
import os

def load_jsonl(path):
    promos = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                promos.append(json.loads(line))
    return promos

def get_latest_two(bank_prefix):
    files = sorted(glob.glob(f"outputs/{bank_prefix}-*.jsonl"), key=os.path.getmtime, reverse=True)
    if len(files) < 2:
        return None, None
    return files[1], files[0]

def stats(bank_prefix, bank_name):
    old_path, new_path = get_latest_two(bank_prefix)
    if not old_path or not new_path:
        print(f"Skipping {bank_name}, missing files.")
        return

    old_promos = load_jsonl(old_path)
    new_promos = load_jsonl(new_path)
    
    old_fixed = sum(1 for p in old_promos if p.get('cashbackType') == 'FIXED' and float(p.get('cashbackValue', 0) or 0) > 500)
    new_fixed = sum(1 for p in new_promos if p.get('cashbackType') == 'FIXED' and float(p.get('cashbackValue', 0) or 0) > 500)
    
    old_rec = sum(1 for p in old_promos if p.get('recommendationScope') == 'RECOMMENDABLE')
    new_rec = sum(1 for p in new_promos if p.get('recommendationScope') == 'RECOMMENDABLE')
    
    old_catalog = sum(1 for p in old_promos if p.get('recommendationScope') == 'CATALOG_ONLY')
    new_catalog = sum(1 for p in new_promos if p.get('recommendationScope') == 'CATALOG_ONLY')
    
    print(f"=== {bank_name} 統計 ===")
    print(f"從 {os.path.basename(old_path)} -> {os.path.basename(new_path)}")
    print(f"總擷取數: {len(old_promos)} -> {len(new_promos)}")
    print(f"RECOMMENDABLE 數量 (會進排名): {old_rec} -> {new_rec} (過濾掉 {old_rec - new_rec} 筆無效/危險資料)")
    print(f"CATALOG_ONLY 數量: {old_catalog} -> {new_catalog} (降級增加 {new_catalog - old_catalog} 筆)")
    print(f"超高額 Fixed 回饋 (>500元): {old_fixed} -> {new_fixed} (修正 {old_fixed - new_fixed} 筆「優惠價」誤判)\n")

stats('cathay-real', '國泰 (CATHAY)')
stats('esun-real', '玉山 (ESUN)')
stats('ctbc-real', '中信 (CTBC)')
stats('taishin-real', '台新 (TAISHIN)')
stats('fubon-real', '富邦 (FUBON)')
