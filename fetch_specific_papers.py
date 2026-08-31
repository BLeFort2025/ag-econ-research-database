import os
import requests
import fitz

dois = [
    '10.2307/1242720',
    '10.1016/0305-750x(92)90058-4',
    '10.1016/0169-5150(89)90008-x',
    '10.1111/j.1477-9552.2000.tb01221.x',
    '10.2307/1242349',
    '10.1111/1477-9552.12221',
    '10.1016/j.foodpol.2016.12.007',
    '10.1111/j.1574-0862.2007.00239.x',
    '10.1111/j.1477-9552.1997.tb01144.x',
    '10.1093/ajae/aaw059'
]

out_dir = "extracted_texts"
os.makedirs(out_dir, exist_ok=True)

for doi in dois:
    safe_doi = doi.replace('/', '_')
    txt_path = os.path.join(out_dir, f"{safe_doi}.txt")
    
    if os.path.exists(txt_path):
        print(f"Skipping {doi}, already extracted.")
        continue
        
    print(f"Processing {doi}...")
    
    api_url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    try:
        resp = requests.get(api_url, timeout=10).json()
        oa = resp.get('open_access', {})
        pdf_url = oa.get('oa_url')
        if not pdf_url:
            print(f"  No Open Access URL found for {doi}")
            continue
            
        print(f"  Found PDF URL: {pdf_url}")
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        pdf_resp = requests.get(pdf_url, stream=True, timeout=20, headers=headers)
        pdf_resp.raise_for_status()
        pdf_path = os.path.join(out_dir, f"{safe_doi}.pdf")
        with open(pdf_path, 'wb') as f:
            for chunk in pdf_resp.iter_content(chunk_size=8192):
                f.write(chunk)
                
        print(f"  Extracting text...")
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)
            
        print(f"  Success.")
    except Exception as e:
        print(f"  Error processing {doi}: {e}")

