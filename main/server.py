from flask import Flask, request
import os
import requests
from bs4 import BeautifulSoup
from mimetypes import guess_extension
from urllib.parse import urljoin  


app = Flask(__name__)

@app.route('/')
def working():
    return "working..."

from requests.exceptions import ConnectionError

@app.route('/url')
def get_url_n_img():
    url = request.args.get('url', default='', type=str)
    output_folder = "./imgs"

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    try:
        response = requests.get(url)
        if response.status_code != 200:
            return "connection error 1"
    except ConnectionError:
        return "connection error 2"

    soup = BeautifulSoup(response.content, "html.parser")

    img_tags = soup.find_all("img")

    for i, img in enumerate(img_tags):
        if not img.has_attr('alt'):
            img_url = img.get("src")
            if img_url:
                try:
                    full_img_url = urljoin(url, img_url)  
                    img_response = requests.get(full_img_url, stream=True)
                    if img_response.status_code == 200:
                        img_content_type = img_response.headers['Content-Type']
                        img_extension = guess_extension(img_content_type)
                        img_name = f"{i}{img_extension}"
                        img_path = os.path.join(output_folder, img_name)
                        with open(img_path, "wb") as img_file:
                            for chunk in img_response.iter_content(chunk_size=8192):
                                img_file.write(chunk)
                        print(f"download: {img_path}")
                except ConnectionError:
                    print(f"Failed to download image at {img_url}")

    return f"url: {url}, download done"

@app.route('/output')
def output_json():
    with open('./responses/output.json', 'r', encoding='utf-8') as file:
        data = file.read()

    from flask import Response
    return Response(data, mimetype='application/json')

if __name__ == '__main__':
    app.run(debug=True, port=9990)