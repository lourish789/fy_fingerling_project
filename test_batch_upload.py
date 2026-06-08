import requests
import os
import time
import base64

def test_upload_batch():
    url = 'http://localhost:5000/api/upload_batch'
    image_dir = 'data/fish_fingerling_yolo/images/train/'
    images = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))][:3]
    
    if not images:
        print('Failure: No images found in training directory.')
        return

    files = []
    for img in images:
        files.append(('files', (img, open(os.path.join(image_dir, img), 'rb'), 'image/jpeg')))

    print(f'Uploading {len(images)} images to {url}...')
    try:
        response = requests.post(url, files=files)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f'Failure: Request failed: {e}')
        return

    # Check results
    success = True
    results = data.get('results', [])
    summary = data.get('summary', {})

    if not results:
        print('Failure: No results in response.')
        success = False
    
    for res in results:
        img_name = res.get('filename')
        # Check annotated_image
        if 'annotated_image' in res and res['annotated_image']:
            try:
                base64.b64decode(res['annotated_image'])
            except Exception:
                print(f'Failure: Invalid base64 in annotated_image for {img_name}')
                success = False
        else:
            print(f'Failure: Missing annotated_image for {img_name}')
            success = False

        # Check per-image counts
        if 'counts' not in res or not isinstance(res['counts'], dict):
            print(f'Failure: Missing or invalid counts for {img_name}')
            success = False

    # Check batch totals
    if 'total_counts' not in summary or not isinstance(summary['total_counts'], dict):
        print('Failure: Missing or invalid batch total_counts in summary.')
        success = False

    if success:
        print('Success: All checks passed.')
        print(f'Batch ID: {data.get("batch_id")}')
        print(f'Summary Counts: {summary.get("total_counts")}')
    else:
        print('Failure: One or more checks failed.')

if __name__ == '__main__':
    test_upload_batch()
