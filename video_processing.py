from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess,sys


def download_segment(CACHE_FOLDER, url: str, order: int, name_prefix: str = "" ):

    print(f"Downloading {name_prefix} - {order}")

    video_download_command = (f".\\aria2c -o '{CACHE_FOLDER}/{name_prefix}-{order}.mp4'"
                              f" -x 16 -s 16 '{url}' -c -l aria2c_video.log --log-level warn")
    result = subprocess.run(['powershell', '-Command', video_download_command], text=True)

    return result

def download_segment_m3u8(CACHE_FOLDER, url: str, order: int, name_prefix: str = "" ):

    print(f"Downloading {name_prefix} - {order}")

    video_download_command = (f".\\ffmpeg -i '{url}' -c copy -n '{CACHE_FOLDER}/{name_prefix}-{order}.mp4'"
                              f" -hide_banner -loglevel error -stats")

    result = subprocess.run(['powershell', '-Command', video_download_command], text=True)

    return result


def download_segments_in_parallel(fallback_flag, CACHE_FOLDER, lesson_video_data, name_prefix):
    has_error = False

    if fallback_flag:
        # Create a ThreadPoolExecutor to manage parallel downloads
        with ThreadPoolExecutor(max_workers=6) as executor:
             # Dictionary to hold future results
            if 'm3u8' in lesson_video_data['data']['live_timeline'][0]['replay_url']:
                future_to_order = {
                    executor.submit(download_segment_m3u8, CACHE_FOLDER, segment['replay_url'], order, name_prefix): order
                    for order, segment in enumerate(lesson_video_data['data']['live_timeline'])
                }
            else:
                future_to_order = {
                    executor.submit(download_segment, CACHE_FOLDER, segment['replay_url'], order, name_prefix): order
                    for order, segment in enumerate(lesson_video_data['data']['live_timeline'])
                }

            # Iterate over the completed futures
            for future in as_completed(future_to_order):
                order = future_to_order[future]
                try:
                    future.result()  # Get the result (will raise exception if there was one)
                    print(f"Successfully downloaded {name_prefix} - {order}")
                except Exception as e:
                    print(e)
                    print(f"Failed to download {name_prefix} - {order}", file=sys.stderr)
                    has_error = True

    else:
        # Create a ThreadPoolExecutor to manage parallel downloads
        with ThreadPoolExecutor(max_workers=6) as executor:
            # Dictionary to hold future results
            if 'm3u8' in lesson_video_data['data']['live'][0]['url']:
                future_to_order = {
                    executor.submit(download_segment_m3u8, CACHE_FOLDER, segment['url'], order, name_prefix): order
                    for order, segment in enumerate(lesson_video_data['data']['live'])
                }
            else:
                future_to_order = {
                    executor.submit(download_segment, CACHE_FOLDER, segment['url'], order, name_prefix): order
                    for order, segment in enumerate(lesson_video_data['data']['live'])
                }

            # Iterate over the completed futures
            for future in as_completed(future_to_order):
                order = future_to_order[future]
                try:
                    future.result()  # Get the result (will raise exception if there was one)
                    print(f"Successfully downloaded {name_prefix} - {order}")
                except Exception as e:
                    print(e)
                    print(f"Failed to download {name_prefix} - {order}", file=sys.stderr)
                    has_error = True

    return has_error


def concatenate_segments(CACHE_FOLDER, DOWNLOAD_FOLDER, name_prefix, num_segments):

    with open(f"{CACHE_FOLDER}/concat.txt", "w", encoding='utf-8') as f:
        f.write("\n".join(
            [f"file '../{CACHE_FOLDER}/{name_prefix}-{i}.mp4'" for i in range(num_segments)]
        ))

    video_concatenating_command = (
        f"ffmpeg -f concat -safe 0 -hwaccel cuda -hwaccel_output_format cuda "
        f"-i '{CACHE_FOLDER}/concat.txt' "
        f"-c:v hevc_nvenc -cq 28 -surfaces 64 -bufsize 12800k -r 7.5 -rc-lookahead 63 "
        f"-c:a aac -ac 1 -rematrix_maxval 1.0 -b:a 64k '{DOWNLOAD_FOLDER}/{name_prefix}.mp4' -n "
        f"-hide_banner -loglevel warning -stats")

    subprocess.run(['powershell', '-Command', video_concatenating_command], text=True)