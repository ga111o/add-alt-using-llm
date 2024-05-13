from iso639 import Language
from joblib import Memory
from langchain.agents import initialize_agent
from langchain.chat_models import ChatOllama, ChatOpenAI
from langchain.callbacks import StreamingStdOutCallbackHandler
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langchain_community.embeddings import HuggingFaceEmbeddings
from transformers import AutoTokenizer, AutoModelForCausalLM

from tools import ImageCaptionTool, ObjectDetectionTool

from transformers import BlipProcessor, BlipForConditionalGeneration, DetrImageProcessor, DetrForObjectDetection
from PIL import Image
import torch

import os
import json
import tempfile

def get_image_caption(image_path):
    """
    Generates a short caption for the provided image.

    Args:
        image_path (str): The path to the image file.

    Returns:
        str: A string representing the caption for the image.
    """
    image = Image.open(image_path).convert('RGB')

    model_name = "Salesforce/blip-image-captioning-large"

    # 나중에 cuda로 돌린다면, half로 돌리는 게 좋을듯
    # processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-large")
    # model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-large", torch_dtype=torch.float16).to("cuda")
    device = "cpu"

    processor = BlipProcessor.from_pretrained(model_name)
    model = BlipForConditionalGeneration.from_pretrained(model_name).to(device)

    inputs = processor(image, return_tensors='pt').to(device)
    output = model.generate(**inputs, max_new_tokens=20)

    caption = processor.decode(output[0], skip_special_tokens=True)

    return caption

def detect_objects(image_path):
    """
    Detects objects in the provided image.

    Args:
        image_path (str): The path to the image file.

    Returns:
        str: A string with all the detected objects. Each object as '[x1, x2, y1, y2, class_name, confindence_score]'.
    """
    image = Image.open(image_path).convert('RGB')

    processor = DetrImageProcessor.from_pretrained("facebook/detr-resnet-50")
    model = DetrForObjectDetection.from_pretrained("facebook/detr-resnet-50")

    inputs = processor(images=image, return_tensors="pt")
    outputs = model(**inputs)

    target_sizes = torch.tensor([image.size[::-1]])
    results = processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.9)[0]

    detections = ""
    for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
        detections += '[{}, {}, {}, {}]'.format(int(box[0]), int(box[1]), int(box[2]), int(box[3]))
        detections += ' {}'.format(model.config.id2label[int(label)])
        detections += ' {}\n'.format(float(score))

    return detections


tools = [ImageCaptionTool(), ObjectDetectionTool()]

conversational_memory = ConversationBufferWindowMemory(
    memory_key='chat_history',
    k=0,
    return_messages=True
)

llm = ChatOpenAI(
    temperature=0.1,
    streaming=True,
    callbacks=[StreamingStdOutCallbackHandler()],
)

# from transformers import AutoTokenizer, AutoModelForCausalLM

# tokenizer = AutoTokenizer.from_pretrained("psymon/KoLlama2-7b")
# model = AutoModelForCausalLM.from_pretrained("psymon/KoLlama2-7b")

# model_name = "psymon/KoLlama2-7b"
# model_kwargs = {'device': 'cpu'}
# encode_kwargs = {'normalize_embeddings': False}
# llm = HuggingFaceEmbeddings(
#     model=model,
#     model_kwargs=model_kwargs,
#     encode_kwargs=encode_kwargs
# )

# llm = ChatOllama(
#     model = "llama3:8b",
#     temperature=0.1,
#     streaming=True,
#     callbacks=[StreamingStdOutCallbackHandler()]
# )

agent = initialize_agent(
    agent="chat-conversational-react-description",
    tools=tools,
    llm=llm,
    max_iterations=5,
    verbose=True,
    memory=conversational_memory,
    early_stopping_method='generate'
)

if not os.path.exists('responses/'):
    os.makedirs('responses/')

with open('responses/input.json', 'r', encoding='utf-8') as file:
    image_info = json.load(file)

image_files = list(image_info.keys())

# todo
# 이 파트 함수든 뭐든으로 만들어서 깔끔하게 정리
for image_name in image_files:
    context = image_info[image_name]["context"]
    language = image_info[image_name]["language"]
    user_question = f"Describe the visual elements of the image in one line based {context}. and translate to {language}"

    tools = [ImageCaptionTool(), ObjectDetectionTool()]

    original_image_path = os.path.join('imgs', image_name)
    print("---original img path:", original_image_path)

    if not os.path.exists(original_image_path):
        print(f"---can't find: {original_image_path}")
        continue

    try:
        with Image.open(original_image_path) as img:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                img.save(tmp.name)
                image_path = tmp.name
                print("---temp img path:", image_path)
                try:
                    print(f'===========user question: {user_question}')
                    response = agent.run(f'{user_question}, image path: {image_path}')
                except FileNotFoundError as e:
                    print(f"can't open: {e}")   
    except FileNotFoundError as e:
        print(f"can't open: {e}")
        continue

    print("---response:", response)
    
    response_file_path = os.path.join('responses', "output.json")
    
    if os.path.exists(response_file_path):
        with open(response_file_path, 'r', encoding='utf-8') as file:
            try:
                data = json.load(file)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}
    
    data[image_name] = {"image_name": image_name, "response": response}
    
    with open(response_file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
