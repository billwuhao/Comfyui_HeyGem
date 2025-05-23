import os
import time
import uuid
import torchaudio
import tempfile
from typing import Optional
import torch
import requests
import json
from tqdm import tqdm

from .heygem_utils import (
    video_to_tensor,
    repeat_or_pingpong_video_tensor,
    )

from .xgc_heygem_utils import (
    start_heygem_service, 
    stop_heygem_service,
    )

TEMP_DIR = "/code/data/face2face"


def cache_audio_tensor(
    cache_dir,
    audio_tensor: torch.Tensor,
    sample_rate: int,
    filename_prefix: str = "cached_audio_",
    audio_format: Optional[str] = ".wav"
) -> str:
    try:
        with tempfile.NamedTemporaryFile(
            prefix=filename_prefix,
            suffix=audio_format,
            dir=cache_dir,
            delete=False 
        ) as tmp_file:
            temp_filepath = tmp_file.name
        
        torchaudio.save(temp_filepath, audio_tensor, sample_rate)

        return temp_filepath
    except Exception as e:
        raise Exception(f"Error caching audio tensor: {e}")


SERVICE_DICT = {
   9999: 'System abnormality',
   10000: 'Succeeded',
   10001: 'Engaged in another task',
   10002: 'Parameter exception',
   10003: 'Get lock exception',
   10004: 'Task does not exist',
   10005: 'Task processing timeout',
   10006: 'Unable to submit task, please check service status',
}

class HeyGemRun:
    @classmethod
    def INPUT_TYPES(s):
        return {"required":
                    {
                        "audio": ("AUDIO",),
                        "video": ("IMAGE", ),
                        "mode": (['normal', 'pingpong', 'repeat'], {"default": "normal"}),
                     },
            "optional": {
                 "stop_heygem": ("BOOLEAN", {"default": False}),
                 "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 60.0, "step": 1.0}),
            },
                }

    CATEGORY = "🎤MW/MW-HeyGem"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("VIDEO",)

    FUNCTION = "run"

    def run(self, video, audio, mode, fps, stop_heygem=False):
        start_heygem_service(TEMP_DIR)

        taskcode = f"{uuid.uuid4()}"

        audio_path = cache_audio_tensor(
            cache_dir=os.path.join(TEMP_DIR, "temp"),
            audio_tensor=audio["waveform"].squeeze(0),
            sample_rate=audio["sample_rate"]
        )
        duration = audio["waveform"].shape[-1] / audio["sample_rate"]

        if mode == "pingpong":
            video = repeat_or_pingpong_video_tensor(video, duration, mode="pingpong", fps=fps)
        elif mode == "repeat":
            video = repeat_or_pingpong_video_tensor(video, duration, mode="repeat", fps=fps)

        video_path = os.path.join(TEMP_DIR, "temp", f"{taskcode}.mp4")
        video.save_to(video_path)
        
        docker_video_path = os.path.join("/code/data/face2face/temp/", f"{taskcode}.mp4")
        docker_audio_path = os.path.join("/code/data/face2face/temp/", os.path.basename(audio_path))
        data = {
            "audio_url": docker_audio_path,
            "video_url": docker_video_path,
            "code": taskcode,
            'watermark_switch': 0,
            'digital_auth': 0,
            'chaofen': 0,
            'pn': 0
        }

        data = json.dumps(data)
        waite_sec = 0
        while waite_sec < 120:
            try:
                post_response = requests.post(url="http://127.0.0.1:8383/easy/submit",data=data)
                if post_response.status_code == 200:
                    result = post_response.json()
                    if result['code'] != 10000:
                        raise ValueError(SERVICE_DICT[result['code']])
                    break
                else:
                    raise Exception(f"Request failed, status code: {post_response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}... \nWait a moment... The service is not ready, try again...")

            time.sleep(3)
            waite_sec += 3

        tq_bar = tqdm(desc="\nHeyGem...")

        while True:
            try:
                get_response = requests.get(url=f"http://127.0.0.1:8383/easy/query?code={taskcode}")
                if get_response.status_code == 200:
                    result = get_response.json()
                    print(result)
                    if result['code'] != 10000:
                        raise ValueError(SERVICE_DICT[result['code']])
                    try:
                        if result['data']['status'] == 2:
                            break
                    except:
                        pass

                else:
                    raise Exception(f"Request failed, status code: {get_response.status_code}")
            except requests.exceptions.RequestException as e:
                raise Exception(f"Request failed: {e}")

            time.sleep(3)
            tq_bar.update(1)

        res_viedo = os.path.join(TEMP_DIR, "temp", f"{taskcode}-r.mp4")

        images_tensor = video_to_tensor(res_viedo)
        if stop_heygem:
            stop_heygem_service()
        return (images_tensor,)



NODE_CLASS_MAPPINGS = {
    "HeyGemRun": HeyGemRun,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "HeyGemRun": "HeyGem AI Avatar",
}