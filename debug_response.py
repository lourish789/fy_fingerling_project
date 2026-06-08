import requests
import os

def check_response():
    url = 'http://localhost:5000/api/upload_batch'
    image_dir = 'data/fish_fingerling_yolo/images/train/'
    images = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))][:1]
    
    files = [('files', (images[0], open(os.path.join(image_dir, images[0]), 'rb'), 'image/jpeg'))]
    
    print('Sending request...')
    response = requests.post(url, files=files)
    print(f'Status: {response.status_code}')
    print(f'Body: {response.text[:500]}')

if __name__ == '__main__':
    check_response()
