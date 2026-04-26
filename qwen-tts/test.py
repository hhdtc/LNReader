import requests
import base64

# 读取参考音频并编码为 Base64
with open("说话-可聪明的人从一开始就不会入局。你瞧，我是不是更聪明一点？.wav", "rb") as f:
    ref_audio_base64 = base64.b64encode(f.read()).decode("utf-8")

url = "http://127.0.0.1:7860/qwenapi/v1/voice-clone"
data = {
    "model_name": "/models/Qwen3-TTS-12Hz-0.6B-Base",
    "text": "你说的对，但是《原神》是由米哈游自主研发的一款全新开放世界冒险游戏。游戏发生在一个被称作「提瓦特」的幻想世界，在这里，被神选中的人将被授予「神之眼」，导引元素之力。你将扮演一位名为「旅行者」的神秘角色，在自由的旅行中邂逅性格各异、能力独特的同伴们，和他们一起击败强敌，找回失散的亲人——同时，逐步发掘「原神」的真相。",
    "ref_audio_base64": ref_audio_base64,
    "language": None,  # 可选,默认自动检测
    "segment_gen": False,  # 可选,是否分段生成,默认为False
}

response = requests.post(url, json=data)
result = response.json()

# 保存生成的音频
for i, audio_base64 in enumerate(result["audio_files_base64"]):
    audio_bytes = base64.b64decode(audio_base64)
    with open(f"output_{i}.wav", "wb") as f:
        f.write(audio_bytes)

print(result["info"])