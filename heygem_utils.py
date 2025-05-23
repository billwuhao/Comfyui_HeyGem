import imageio
import numpy as np
import torch
import subprocess
import os
import sys
import time


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCKER_COMPOSE_FILE = os.path.join(BASE_DIR, "docker-compose-lite.yml")
CONTAINER_NAME = "heygem-gen-video"
VOLUME_ENV_VAR = "HEGEM_FACE2FACE_DATA_PATH"

os.environ['NO_PROXY'] = 'localhost,127.0.0.1,::1'
os.environ['no_proxy'] = 'localhost,127.0.0.1,::1' # 有些库可能只认小写

def _run_docker_command(command_parts, check_result=False, capture_output=True, text_output=True, env=None):
    """
    内部辅助函数，用于执行 Docker 或 Docker Compose 命令。
    """
    try:
        result = subprocess.run(
            command_parts,
            capture_output=capture_output,
            text=text_output,
            check=check_result,
            env=env
        )
        return result
    except FileNotFoundError:
        print(f"Error: '{command_parts[0]}' command not found.", file=sys.stderr)
        print(f"Please ensure Docker or Docker Compose is installed and in your system's PATH.", file=sys.stderr)
        raise # 重新抛出异常，让调用者处理
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {' '.join(e.cmd)}", file=sys.stderr)
        print(f"Exit Code: {e.returncode}", file=sys.stderr)
        if e.stdout: print(f"Stdout:\n{e.stdout}", file=sys.stderr)
        if e.stderr: print(f"Stderr:\n{e.stderr}", file=sys.stderr)
        raise # 重新抛出异常
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        raise # 重新抛出异常

def is_docker_container_running(container_name):
    """
    检查指定名称的 Docker 容器是否正在运行。
    这个检查是全局性的，不局限于某个 compose 文件。
    """
    print(f"Checking if container '{container_name}' is currently running...")
    command = [
        "docker", "ps",
        "-q",  # 只输出容器ID
        "--filter", f"name={container_name}" # 过滤出指定名称的容器
    ]
    try:
        result = _run_docker_command(command)
        if result.stdout.strip():
            print(f"Container '{container_name}' is running (ID: {result.stdout.strip()}).")
            return True
        else:
            return False
    except Exception:
        raise

# def is_docker_service_ready(
#     container_name: str,
#     timeout: int = 300,
#     polling_interval: int = 5
# ) -> bool:
#     """
#     检查指定名称的 Docker 容器内的服务是否已启动并准备好工作，
#     通过尝试连接到服务URL中的主机和端口。

#     :param container_name: Docker 容器的名称。
#     :param timeout: 等待服务准备就绪的总超时时间（秒）。
#     :param polling_interval: 检查服务状态的间隔时间（秒）。
#     :return: 如果容器在超时时间内运行且端口开放，则返回 True；否则返回 False。
#     """
#     import socket
#     from urllib.parse import urlparse
#     parsed_url = urlparse("http://127.0.0.1:8383")
#     host = parsed_url.hostname
#     port = parsed_url.port

#     start_time = time.time()
#     while time.time() - start_time < timeout:
#         # 1. 检查容器是否正在运行
#         if not is_docker_container_running(container_name):
#             print(f"Container '{container_name}' is not running. Waiting {polling_interval}s...")
#             time.sleep(polling_interval)
#             continue

#         # 2. 容器正在运行，尝试检查端口是否开放
#         print(f"Attempting to connect to {host}:{port}...")
#         try:
#             with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#                 s.settimeout(polling_interval) # 设置连接超时，避免长时间阻塞
#                 # connect_ex() 返回 0 表示成功，否则是错误码
#                 result = s.connect_ex((host, port))
#                 if result == 0:
#                     print(f"Port {port} on {host} is open for '{container_name}'. Service is deemed ready.")
#                     return True
#                 else:
#                     # errno.ECONNREFUSED (111 on Linux) if nothing listening
#                     print(f"Port {port} on {host} is not open for '{container_name}' (Error code: {result}). Waiting {polling_interval}s...")
#         except Exception as e:
#             # 捕获其他任何socket相关的错误（如主机名解析失败等）
#             print(f"An unexpected error occurred during port check for {host}:{port}: {e}. Waiting {polling_interval}s...")

#         time.sleep(polling_interval)

#     print(f"Timeout ({timeout}s) reached. Service in '{container_name}' did not become ready (port not open).")
#     return False

def docker_container_exists(container_name):
    """
    检查指定名称的 Docker 容器是否存在（无论运行或停止）。
    """
    print(f"Checking if container '{container_name}' exists...")
    command = [
        "docker", "ps",
        "-aq", # 输出所有容器ID，包括停止的
        "--filter", f"name={container_name}" # 过滤出指定名称的容器
    ]
    try:
        result = _run_docker_command(command)
        if result.stdout.strip():
            print(f"Container '{container_name}' exists (ID: {result.stdout.strip()}).")
            return True
        else:
            print(f"Container '{container_name}' does not exist.")
            return False
    except Exception:
        return False # 如果执行命令本身出错，就认为不存在

def start_heygem_service(volume_host_path):
    """
    启动 heygem-gen-video Docker 容器/服务。
    优先尝试直接启动已存在的容器，否则通过 docker-compose 创建和启动。
    """
    print(f"\n--- Attempting to start '{CONTAINER_NAME}' service ---")
    
    # 优先级 1: 检查同名容器是否已经运行
    if is_docker_container_running(CONTAINER_NAME):
        print(f"\nContainer '{CONTAINER_NAME}' is already running. No action needed.")
        return True

    # 优先级 2: 检查同名容器是否存在但已停止，并尝试直接启动
    if docker_container_exists(CONTAINER_NAME):
        print(f"\nContainer '{CONTAINER_NAME}' exists but is stopped. Attempting to start it directly...")
        start_command = ["docker", "start", CONTAINER_NAME]
        try:
            _run_docker_command(start_command, check_result=True)
            print(f"Successfully sent 'docker start {CONTAINER_NAME}' command.")
            
            time.sleep(5)
            # 验证是否启动成功
            if is_docker_container_running(CONTAINER_NAME):
                print(f"Container '{CONTAINER_NAME}' confirmed as running after direct start.")
                return True
            else:
                print(f"Container '{CONTAINER_NAME}' did not become ready after direct start.")
                return False

        except Exception:
            print(f"Failed to directly start container '{CONTAINER_NAME}'. Falling back to docker-compose.", file=sys.stderr)
            # 如果直接启动失败，继续尝试使用 docker-compose (可能容器损坏或其他问题)
            pass 

    # 优先级 3: 如果容器不存在或直接启动失败，使用 docker-compose 创建并启动
    print(f"\nContainer '{CONTAINER_NAME}' not found or failed direct start. Using docker-compose to create and start it...")
    # --- 增加 Docker Daemon 检查逻辑 ---
    print("\nChecking if Docker daemon is running and reachable...")
    docker_daemon_running = False
    try:
        # Use a simple command like 'docker info' to check if the daemon is reachable
        # check_result=True will raise an exception if the command fails (e.g., cannot connect)
        _run_docker_command(["docker", "info"], check_result=True)
        docker_daemon_running = True
        print("Docker daemon is running and reachable.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        # Catch specific errors indicating Docker command failed or not found.
        print("\n--- Docker Daemon Not Running ---", file=sys.stderr)
        print("Error: Could not connect to the Docker daemon.", file=sys.stderr)
        print("Cannot proceed with docker-compose without a running Docker daemon.", file=sys.stderr)
        print("\nPlease ensure the Docker daemon is running:", file=sys.stderr)

        # Provide platform-specific hints
        if sys.platform.startswith('linux'):
            print("  - On Linux, try: 'sudo systemctl start docker' or 'sudo service docker start'", file=sys.stderr)
        elif sys.platform == 'win32': # Running on Windows native or possibly within WSL talking to Windows Docker Desktop
             print("  - On Windows with Docker Desktop: Ensure Docker Desktop application is running.", file=sys.stderr)
             print("  - If running within WSL: Ensure Docker Desktop on Windows is running and WSL integration is enabled.", file=sys.stderr)
        elif sys.platform == 'darwin': # macOS
             print("  - On macOS: Ensure Docker Desktop application is running.", file=sys.stderr)
        else:
             print("  - Please consult your operating system documentation for starting the Docker service.", file=sys.stderr)

        print("-----------------------------------", file=sys.stderr)

        # We cannot proceed without the daemon
        raise

    # --- 结束 Docker Daemon 检查逻辑 ---

    # Proceed with docker-compose ONLY if the daemon is confirmed running
    if docker_daemon_running:
        print(f"\nUsing docker-compose to create and start container '{CONTAINER_NAME}'...")
        print(f"Docker Compose file: {DOCKER_COMPOSE_FILE}")
        print(f"Volume host path to use: {volume_host_path}")

        env_for_subprocess = os.environ.copy()
        env_for_subprocess[VOLUME_ENV_VAR] = volume_host_path
        env_for_subprocess['PWD'] = os.getcwd()

        # Use "docker compose" for newer Docker versions, "docker-compose" for older
        # Sticking to 'docker-compose' as in the original request.
        compose_up_command = [
            "docker-compose",
            "-f",
            DOCKER_COMPOSE_FILE,
            "up",
            "-d"
        ]

        # --- MODIFICATION STARTS HERE: Execute docker-compose command directly ---
        print(f"\nExecuting command: {' '.join(compose_up_command)}")
        print("-" * 30) # Separator to distinguish output
        try:
            # Execute docker-compose command using subprocess.run directly.
            # stdout=sys.stdout and stderr=sys.stderr will stream the output
            # directly to the console as it happens.
            # check=True ensures that if the command fails, a CalledProcessError is raised.
            subprocess.run(
                compose_up_command,
                check=True,
                env=env_for_subprocess,
                stdout=sys.stdout, # Stream stdout
                stderr=sys.stderr  # Stream stderr
            )
            print("-" * 30) # Separator after command output

            # No need to print stdout/stderr from a result object, as it was streamed live.
            print(f"\nSuccessfully executed 'docker-compose up -d' for '{CONTAINER_NAME}'.")

            # --- MODIFICATION ENDS HERE ---

            # Validation check (Remains the same)
            print(f"\nWaiting for container '{CONTAINER_NAME}' to become ready...")

            wait_sec = 0
            max_wait_sec = 60
            wait_interval_sec = 3

            while wait_sec < max_wait_sec:
                if is_docker_container_running(CONTAINER_NAME):
                    print(f"Container '{CONTAINER_NAME}' confirmed as running after docker-compose up.")
                    return True

                # Check container status more explicitly during wait (Use helper here as output is captured)
                try:
                    status_command = ["docker", "inspect", "-f", "{{.State.Status}}", CONTAINER_NAME]
                    # Using _run_docker_command as we just need the status string
                    status_result = _run_docker_command(status_command)
                    status = status_result.stdout.strip()
                    print(f"Container status: '{status}'. Waiting for 'running'... (Waited {wait_sec}/{max_wait_sec}s)")
                except Exception:
                    print(f"Could not inspect container status. Waiting... (Waited {wait_sec}/{max_wait_sec}s)")


                time.sleep(wait_interval_sec)
                wait_sec += wait_interval_sec

            # Timed out (Remains the same)
            print(f"\nError: Timed out waiting for container '{CONTAINER_NAME}' to start after docker-compose up ({max_wait_sec}s).", file=sys.stderr)
            print("Please check container logs for details (e.g., 'docker logs {}').".format(CONTAINER_NAME), file=sys.stderr)
            return False

        except Exception: # Catch errors during the subprocess.run command itself (including CalledProcessError)
            print(f"\nFailed to start '{CONTAINER_NAME}' using docker-compose. The command output above should provide details.", file=sys.stderr)
            # The actual error messages from docker-compose were already streamed to stderr by subprocess.run
            return False

    else:
         # This part is technically unreachable because we return False if the daemon check fails,
         # but kept for logical completeness.
         print("Skipping docker-compose up because Docker daemon is not running.", file=sys.stderr)
         return False

def _get_container_id(container_name):
    """
    获取指定名称的容器ID，如果容器不存在或不运行，则返回None。
    """
    command = [
        "docker", "ps",
        "-q",  # 只输出容器ID
        "--filter", f"name={container_name}" # 过滤出指定名称的容器
    ]
    try:
        result = _run_docker_command(command)
        container_id = result.stdout.strip()
        if container_id:
            return container_id
        return None
    except Exception as e:
        print(f"Error getting container ID for '{container_name}': {e}", file=sys.stderr)
        return None
       
def stop_heygem_service():
    """
    停止 heygem-gen-video Docker 容器。
    优先尝试使用 'docker stop <container_name>' 命令。
    如果服务未运行，则跳过停止操作。
    """
    print(f"\n--- Attempting to stop '{CONTAINER_NAME}' service ---")

    # 检查容器是否运行 (无论是 compose 启动的还是直接启动的)
    current_container_id = _get_container_id(CONTAINER_NAME)
    if not current_container_id:
        print(f"\nContainer '{CONTAINER_NAME}' is not running. No need to stop.")
        return True

    print(f"\nContainer '{CONTAINER_NAME}' is running (ID: {current_container_id}). Attempting to stop it...")

    # 尝试使用 docker stop 命令
    stop_command = ["docker", "stop", current_container_id] # 使用获取到的ID更精确

    try:
        print(f"\nExecuting command: {' '.join(stop_command)}")
        _run_docker_command(stop_command, check_result=True)
        print(f"\nSuccessfully sent 'docker stop {CONTAINER_NAME}' command.")

    except Exception as e:
        print(f"\nFailed to stop '{CONTAINER_NAME}' using 'docker stop': {e}. Please check the logs above.", file=sys.stderr)

def save_tensor_as_video_lossless(image_tensor, output_path, duration, mode='normal', fps=24):
    """
    将形状为 [frames, height, width, channels] 的 PyTorch 张量保存为视频文件，
    尝试最小化损失，并根据指定的持续时间和模式调整帧序列。

    :param image_tensor: 形状为 [frames, height, width, channels] 的 PyTorch 张量，范围为 [0, 1]
    :param output_path: 输出视频文件路径 (建议使用 .mkv, .avi 或 .mov 扩展名以支持更多无损编码)
    :param duration: 输出视频的持续时间（秒）。必须为正数。
    :param mode: 视频播放模式。可选值为 'normal', 'pingpong', 'repeat'。
                 - 'normal': 如果原始视频长度大于duration，则截断。如果小于或等于，则播放原始长度。
                             此模式下，duration作为上限，视频不会被延长。
                 - 'pingpong': 将视频像乒乓球一样来回播放 (frame0 -> frame1 -> ... -> last -> second_last -> ... -> frame1 -> frame0 -> ...)，
                               直到达到指定的 duration。
                 - 'repeat': 重复播放整个视频 (frame0 -> ... -> last -> frame0 -> ...)，直到达到指定的 duration。
    :param fps: 视频帧率
    """
        
    original_frames_count = image_tensor.shape[0]

    # 计算目标总帧数
    target_frames_count = int(duration * fps)
    # --- 准备帧序列 ---
    # 确保张量在 CPU 上
    if image_tensor.is_cuda:
        tensor_np = image_tensor.cpu().numpy()
    else:
        tensor_np = image_tensor.numpy()

    # 将张量值从 [0, 1] 范围转换为 [0, 255] 范围，并确保数据类型为 uint8
    # 使用 np.round 进行四舍五入，并使用 np.clip 确保在 [0, 255] 范围内
    tensor_np = np.clip(np.round(tensor_np * 255), 0, 255).astype(np.uint8)

    # 生成需要写入的帧的索引序列
    frame_indices_to_write = []
    original_indices = np.arange(original_frames_count)

    if mode == 'repeat':
        # 重复原始索引序列直到达到目标帧数
        while len(frame_indices_to_write) < target_frames_count:
            frame_indices_to_write.extend(original_indices)
        frame_indices_to_write = frame_indices_to_write[:target_frames_count]

    elif mode == 'pingpong':
        # pingpong 序列： forward, backward (排除首尾帧避免重复)
        forward_indices = original_indices
        backward_indices = original_indices[-2::-1] # 从倒数第二帧到第一帧

        while len(frame_indices_to_write) < target_frames_count:
            frame_indices_to_write.extend(forward_indices)
            frame_indices_to_write.extend(backward_indices)
        frame_indices_to_write = frame_indices_to_write[:target_frames_count]

    # 将索引列表转换为 numpy 数组，方便迭代
    frame_indices_to_write_np = np.array(frame_indices_to_write)

    # --- 视频保存部分 ---
    # 尝试使用FFV1 (无损)
    try:
        # imageio 2.9.0 及更高版本可能需要 explicit 'codec' 参数
        # macro_block_size=1 可以提高编码器精确度，可能略微增大文件，但FFV1已经是无损了
        writer_params = {'codec': 'ffv1'}
        if sys.version_info >= (3, 7): # macro_block_size requires Python 3.7+ for imageio 2.9+
            # Note: macro_block_size might not be supported by all FFV1 versions or configurations
            pass # Let's remove macro_block_size=1 as it's not a standard FFV1 option via imageio
                 # FFV1 is inherently lossless, so this setting might not be needed or supported
            
        with imageio.get_writer(output_path, fps=fps, **writer_params) as writer:
            for idx in frame_indices_to_write_np:
                writer.append_data(tensor_np[idx])
        print(f"Successfully saved video to {output_path} using FFV1 (lossless).")

    except Exception as e:
        print(f"Failed to use FFV1 codec: {e}. Trying libx264 with crf=0 (lossless, but might have YUV conversion).")
        # 尝试使用 libx264, crf=0 (无损)
        try:
            # 'crf=0' 参数通过 ffmpeg_params 传递
            # '-pix_fmt yuv444p' 尝试保留更多色彩信息，避免 YUV 4:2:0 引起的色度下采样损失
            # imageio 的 ffmpeg_params 有时需要列表形式
            ffmpeg_params = ['-crf', '0', '-pix_fmt', 'yuv444p']
            
            with imageio.get_writer(output_path, fps=fps, codec='libx264', ffmpeg_params=ffmpeg_params) as writer:
                for idx in frame_indices_to_write_np:
                     writer.append_data(tensor_np[idx]) # libx264 需要 uint8 范围 [0, 255]

            print(f"Successfully saved video to {output_path} using libx264 (crf=0, lossless).")

        except Exception as e_h264:
            print(f"Failed to use libx264 crf=0: {e_h264}. Falling back to default (potentially lossy).")
            # 最后的退路：使用默认设置，可能会有损
            try:
                with imageio.get_writer(output_path, fps=fps) as writer:
                    for idx in frame_indices_to_write_np:
                        writer.append_data(tensor_np[idx]) # 默认编码器通常也需要 uint8
                print(f"Saved video to {output_path} using default imageio settings (potentially lossy).")
            except Exception as e_default:
                 print(f"Failed even with default settings: {e_default}")
                 print("Video saving failed.")

def repeat_or_pingpong_video_tensor(video_tensor, duration, mode, fps=24):
    """
    将视频张量（形状 [frames, height, width, channels]）根据指定模式和持续时间进行拼接。

    :param video_tensor: 形状为 [frames, height, width, channels] 的 PyTorch 张量。
    :param duration: 输出视频的目标持续时间（秒）。必须为正数。可以是 Python 数字或单元素 PyTorch 张量。
    :param mode: 视频播放模式。可选值为 'pingpong' 或 'repeat'。
                 - 'pingpong': 将视频像乒乓球一样来回播放，直到达到指定的 duration。
                 - 'repeat': 重复播放整个视频，直到达到指定的 duration。
    :param fps: 视频帧率。必须为正数。可以是 Python 数字或单元素 PyTorch 张量。
    :return: 形状为 [target_frames, height, width, channels] 的 PyTorch 张量。
    """
    original_frames_count = video_tensor.shape[0]
    target_frames_count = int(duration * fps)
    original_indices = torch.arange(original_frames_count, device='cpu')
    long_indices_sequence = torch.empty(0, dtype=torch.long) # Initialize empty sequence

    if mode == 'repeat':
        # Repeat the original sequence until target length is met or exceeded
        num_repeats = (target_frames_count + original_frames_count - 1) // original_frames_count
        long_indices_sequence = original_indices.repeat(num_repeats)

    elif mode == 'pingpong':
        forward_indices = original_indices
        # Slice [start:stop:step]. stop is exclusive. Step is -1 for reverse.
        # Start at N-2, go down to index 1.
        backward_indices = original_indices[original_frames_count - 2 : 0 : -1]

        one_cycle = torch.cat((forward_indices, backward_indices))
        cycle_length = len(one_cycle)

        # Repeat the cycle until target length is met or exceeded
        num_cycles = (target_frames_count + cycle_length - 1) // cycle_length
        long_indices_sequence = one_cycle.repeat(num_cycles)

    # 截取到目标帧数 ---
    # Truncate the generated index sequence to the exact target frames count
    final_indices = long_indices_sequence[:target_frames_count]

    # 使用索引构建最终张量 ---
    # Move indices to the same device as the video_tensor for efficient indexing
    final_indices = final_indices.to(video_tensor.device)

    # Use advanced indexing to select frames from the original tensor
    result_tensor = video_tensor[final_indices]

    print(f"Original frames: {original_frames_count}, Target duration: {duration}s, FPS: {fps}, Target frames: {target_frames_count}")
    print(f"Generated video tensor shape: {result_tensor.shape}")

    return result_tensor

# def save_tensor_as_image_sequence(image_tensor, output_dir, filename_prefix="frame", fps=24):
#     """
#     将形状为 [frames, height, width, channels] 的 PyTorch 张量保存为无损图像序列。

#     :param image_tensor: 形状为 [frames, height, width, channels] 的 PyTorch 张量，范围为 [0, 1]
#     :param output_dir: 输出图像序列的目录
#     :param filename_prefix: 文件名前缀
#     :param fps: 视频帧率 (仅用于信息，不影响保存)
#     """
#     if not os.path.exists(output_dir):
#         os.makedirs(output_dir)

#     if image_tensor.is_cuda:
#         tensor_np = image_tensor.cpu().numpy()
#     else:
#         tensor_np = image_tensor.numpy()

#     # 量化到 uint8，四舍五入并裁剪
#     tensor_np = np.clip(np.round(tensor_np * 255), 0, 255).astype(np.uint8)

#     for i, frame in enumerate(tensor_np):
#         output_path = os.path.join(output_dir, f"{filename_prefix}_{i:05d}.png")
#         imageio.imwrite(output_path, frame)
#     print(f"Saved frames as PNG sequence to '{output_dir}/{filename_prefix}_XXXXX.png'.")
#     print(f"You can combine them into a video using FFmpeg: ffmpeg -i {output_dir}/{filename_prefix}_%05d.png -vf fps={fps} output.mkv")

# def load_image_sequence_to_tensor(input_dir, filename_pattern="frame_%05d.png"):
#     """
#     从无损图像序列加载图像并转换为形状为 [frames, height, width, channels] 的 PyTorch 张量。

#     :param input_dir: 包含图像序列的目录
#     :param filename_pattern: 图像文件名模式，例如 "frame_%05d.png"
#     :return: 形状为 [frames, height, width, channels] 的 PyTorch 张量
#     """
#     import glob
#     import re

#     files = sorted(glob.glob(os.path.join(input_dir, filename_pattern.replace('%05d', '*'))))
    
#     frames = []
#     for file_path in files:
#         # 确保按数字顺序读取
#         match = re.search(r'(\d+)\.png$', os.path.basename(file_path))
#         if match:
#             idx = int(match.group(1))
#             # 读取并归一化
#             frame = imageio.imread(file_path)
#             frame_normalized = (frame.astype(np.float32) / 255.0)
#             frames.append((idx, frame_normalized))
    
#     # 确保按索引排序
#     frames.sort(key=lambda x: x[0])
#     frames_np = np.stack([f[1] for f in frames], axis=0)
#     tensor = torch.tensor(frames_np, dtype=torch.float32)
#     print(f"Loaded {len(frames)} frames from '{input_dir}' as tensor.")
#     return tensor

def video_to_tensor(video_path):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件未找到: {video_path}")

    print(f"Attempting to load video: {video_path}")

    reader = None # Initialize reader to None for error handling
    try:
        # 使用 imageio 读取视频文件
        reader = imageio.get_reader(video_path)
        meta = reader.get_meta_data()

        width, height = meta['size']
        # 这里简化为只处理常见的RGB 3通道情况。
        channels = 3
        print(f"Video metadata: {meta.get('nframes', 'unknown')} frames, {width}x{height}, fps={meta.get('fps')}")

        # 这个生成器应该逐帧读取原始 uint8 数据，并将其转换为 float32 [0, 1]
        def frame_processor_generator(imgio_reader, expected_shape):
            """Generator to read, process, and yield frames as float32 [0, 1]."""
            for i, frame in enumerate(imgio_reader):
                # Ensure frame is RGB if it was RGBA (common from imageio)
                if frame.shape[-1] == 4 and expected_shape[-1] == 3:
                     frame = frame[:, :, :3]
                # Basic shape check
                if frame.shape != expected_shape:
                    print(f"Warning: Frame {i} has unexpected shape {frame.shape}. Expected {expected_shape}. Skipping.")
                    continue

                # Convert uint8 frame to float32 [0, 1]
                # Use .copy() for safety with np.fromiter/torch.from_numpy
                frame_processed = (frame.astype(np.float32) / 255.0)

                yield frame_processed # Yield the processed numpy array

        # 这里的 expected_shape 是单帧的 shape (height, width, channels)
        frame_shape = (height, width, channels)
        gen_instance = frame_processor_generator(reader, frame_shape)

        # 使用 np.fromiter 收集所有生成器产生的帧到 NumPy 数组
        # 这是一个主要的内存消耗点，它会尝试将所有帧一次性放入内存
        # dtype 参数定义了生成器yielding的元素的类型和形状
        # 需要捕获 StopIteration 异常，因为 fromiter 会耗尽生成器
        frames_np_flat = np.fromiter(
            gen_instance,
            # Define the dtype for each yielded item: float32, shape (height, width, channels)
            # np.dtype expects shape in (row, col, channel) or similar format, matching frame_processed shape
            np.dtype((np.float32, frame_shape))
        )

        # np.fromiter with a structured dtype like this results in a 1D array where each element is a "view"
        # of the structured type. We need to reshape it into the desired [frames, height, width, channels]
        num_loaded_frames = len(frames_np_flat)

        if num_loaded_frames == 0:
            reader.close()
            raise RuntimeError(f"Failed to load any frames from video '{video_path}'. Check video file.")

        # --- Implementation ---

        # 1. Reader and metadata
        # Done above.

        # 2. Generator function
        # Defined frame_processor_generator above.

        # 3. Instantiate generator and call np.fromiter
        frame_shape = (height, width, channels)
        gen_instance = frame_processor_generator(reader, frame_shape)

        print("Reading frames using generator and np.fromiter...")
        # This line collects all yielded items until StopIteration from the generator
        # and puts them into a 1D numpy array with the specified compound dtype.
        frames_structured_np = np.fromiter(
            gen_instance,
            dtype=np.dtype((np.float32, frame_shape))
        )
        print(f"Finished reading frames. Structured numpy array shape: {frames_structured_np.shape}, dtype: {frames_structured_np.dtype}")

        num_loaded_frames = len(frames_structured_np)

        if num_loaded_frames == 0:
            reader.close()
            raise RuntimeError(f"Failed to load any frames from video '{video_path}'. Check video file or its content.")

        # 4. Convert the 1D structured numpy array to a multi-dimensional array
        # This step is necessary because torch.from_numpy doesn't directly convert
        # a 1D array of compound dtypes into a multi-dimensional tensor in the way needed.
        # We view the underlying data as float32 scalars and reshape.
        # Total number of scalars = num_loaded_frames * height * width * channels
        total_scalars = num_loaded_frames * height * width * channels
        try:
            # Check if the total number of elements in the structured array matches the expected number of scalars
            if frames_structured_np.size * frames_structured_np.dtype.itemsize != total_scalars * np.dtype(np.float32).itemsize:
                 # This check is a bit complex and might not be strictly needed if view works correctly.
                 # The view operation directly reinterprets the memory.
                 pass # Skip complex size check for now, rely on reshape

            # Reshape the view of the data buffer
            frames_np = frames_structured_np.view(np.float32).reshape(-1, height, width, channels)
            print(f"Reshaped numpy array shape: {frames_np.shape}, dtype: {frames_np.dtype}")

        except Exception as reshape_e:
            print(f"Error reshaping numpy array after fromiter: {reshape_e}")
            reader.close()
            raise RuntimeError(f"Failed to reshape frame data loaded from '{video_path}'. Likely mismatch in expected frame dimensions or data.") from reshape_e


        # 5. 将 NumPy 数组转换为 PyTorch 张量
        # This is the second major memory allocation step.
        print("Converting numpy array to torch tensor...")
        try:
            # The numpy array is already float32 [0, 1], so convert directly
            tensor = torch.from_numpy(frames_np)
            print("Tensor conversion successful.")
        except Exception as tensor_e:
            print(f"Error converting numpy array to torch tensor: {tensor_e}")
            # This is where the original OOM error likely occurred, if the reshape step didn't already fail
            reader.close()
            raise RuntimeError(f"Failed to convert numpy array to torch tensor for '{video_path}'. Likely out of memory.") from tensor_e

        # 6. Close the reader
        reader.close()

        print(f"Successfully loaded video '{video_path}' into tensor with shape {tensor.shape}.")
        return tensor

    except Exception as e:
        # Catch potential errors during get_reader or get_meta_data, or any unhandled exceptions above
        print(f"An error occurred during video loading for '{video_path}': {e}")
        # Ensure the reader is closed if it was successfully opened before an error occurred
        if reader is not None:
             try:
                 reader.close()
             except Exception:
                 pass # Ignore errors during closing
        raise # Re-raise the original exception