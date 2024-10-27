import os
import sys
import argparse
import time
import re

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
parser.add_argument("-c", "--session-cookie", help="Session Cookie", required=False)
parser.add_argument("-y", "--ykt-host", help="RainClassroom Host", required=False, default="pro.yuketang.cn")
parser.add_argument("--video", action="store_true", help="Download Video")
parser.add_argument("--ppt", action="store_true", help="Download PPT")
parser.add_argument("--ppt-to-pdf", action="store_true", help="Convert PPT to PDF", default=True)
parser.add_argument("--ppt-problem-answer", action="store_true", help="Store PPT Problem Answer", default=True)
parser.add_argument("--course-name-filter", action="store", help="Filter Course Name", default=None)
parser.add_argument("--lesson-name-filter", action="store", help="Filter Lesson Name", default=None)

# Check for no arguments and display help if none are given
if len(sys.argv) == 1:
    parser.print_help()
    print('\nYOU SHALL RUN THIS EXECUTABLE FROM POWERSHELL WITH ARGUMENT!!')
    print('YOU SHALL RUN THIS EXECUTABLE FROM POWERSHELL WITH ARGUMENT!!')
    print('YOU SHALL RUN THIS EXECUTABLE FROM POWERSHELL WITH ARGUMENT!!')
    sys.exit()

args = parser.parse_args()

# Check if no arguments are provided or only --help is provided
if args.help or len(vars(args)) == 0:
    print("""RainClassroom Video Downloader

requirements:
    - Python >= 3.12
    - requests
    - websocket-client (qrcode login)
    - qrcode (qrcode login)
    - Pillow (Add answer to problem; Convert PPT to PDF)

    - aria2c (Download files multi-threaded & resume support)
    - ffmpeg with nvenc support (Concatenate video segments and convert to HEVC)
""")
    print(parser.format_help())
    exit()

import requests
import json

# --- --- --- Section Init --- --- --- #
# Login to RainClassroom
userinfo = {}
rainclassroom_sess = requests.session()

YKT_HOST = args.ykt_host
DOWNLOAD_FOLDER = "data"
CACHE_FOLDER = "cache"

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(CACHE_FOLDER, exist_ok=True)


# --- --- --- Section Load Session --- --- --- #

if args.session_cookie is not None:
    rainclassroom_sess.cookies['sessionid'] = args.session_cookie

# --- --- --- Section Login --- --- --- #
else:
    import websocket
    import qrcode

    def on_message(ws, message):
        global userinfo
        userinfo = json.loads(message)
        if 'subscribe_status' in userinfo:
            ws.close()
            return

        qr = qrcode.QRCode()
        qr.add_data(userinfo["qrcode"])
        # Flush screen first
        print("\033c")
        qr.print_ascii(out=sys.stdout)
        print("请扫描二维码登录")


    def on_error(ws, error):
        print(error)


    def on_open(ws):
        ws.send(data=json.dumps({"op": "requestlogin", "role": "web", "version": 1.4, "type": "qrcode", "from": "web"}))


    # websocket数据交互
    ws = websocket.WebSocketApp(f"wss://{YKT_HOST}/wsapp/",
                                on_message=on_message,
                                on_error=on_error)
    ws.on_open = on_open
    ws.run_forever()

    # 登录
    req = rainclassroom_sess.get(f"https://{YKT_HOST}/v/course_meta/user_info")
    rainclassroom_sess.post(f"https://{YKT_HOST}/pc/web_login",
                            data=json.dumps({'UserID': userinfo['UserID'], 'Auth': userinfo['Auth']}))

    # Store session
    with open(f"{DOWNLOAD_FOLDER}/session.txt", "a", encoding='utf-8') as f:
        f.write(rainclassroom_sess.cookies['sessionid']+ "\n")

# --- --- --- Section Get Course List --- --- --- #

# 获取自己的课程列表
shown_courses = rainclassroom_sess.get(f"https://{YKT_HOST}/v2/api/web/courses/list?identity=2").json()

hidden_courses = rainclassroom_sess.get(f"https://{YKT_HOST}/v2/api/web/classroom_archive").json()

for course in hidden_courses['data']['classrooms']:
    course['classroom_id'] = course['id']

courses = shown_courses['data']['list'] + hidden_courses['data']['classrooms']

if args.course_name_filter is not None:
    courses = [c for c in courses if args.course_name_filter in c['name']]

rainclassroom_sess.cookies['xtbz'] = 'ykt'


# --- --- --- Section Get Lesson List --- --- --- #


def get_lesson_list(course: dict, name_prefix: str = ""):
    lesson_data = rainclassroom_sess.get(
        f"https://{YKT_HOST}/v2/api/web/logs/learn/{course['classroom_id']}?actype=14&page=0&offset=500&sort=-1").json()

    folder_name = f"{course['name']}-{course['teacher']['name']}"

    # Rename old folder
    if os.path.exists(f"{DOWNLOAD_FOLDER}/{course['name']}"):
        os.rename(f"{DOWNLOAD_FOLDER}/{course['name']}", f"{DOWNLOAD_FOLDER}/{folder_name}")

    if os.path.exists(f"{CACHE_FOLDER}/{course['name']}"):
        os.rename(f"{CACHE_FOLDER}/{course['name']}", f"{CACHE_FOLDER}/{folder_name}")

    os.makedirs(f"{DOWNLOAD_FOLDER}/{folder_name}", exist_ok=True)
    os.makedirs(f"{CACHE_FOLDER}/{folder_name}", exist_ok=True)

    name_prefix += folder_name.rstrip() + "/"
    # Remove illegal characters for Windows filenames
    name_prefix = re.sub(r'[<>:"\\|?*]', '_', name_prefix)

    if args.lesson_name_filter is not None:
        lesson_data['data']['activities'] = [l for l in lesson_data['data']['activities'] if
                                             args.lesson_name_filter in l['title']]

    length = len(lesson_data['data']['activities'])

    if args.video:
        for index, lesson in enumerate(lesson_data['data']['activities']):
            lesson['classroom_id'] = course['classroom_id']

            # Lesson
            try:
                download_lesson_video(lesson, name_prefix + str(length - index))
            except Exception as e:
                print(e)
                print(f"Failed to download video for {name_prefix} - {lesson['title']}", file=sys.stderr)

    if args.ppt:
        for index, lesson in enumerate(lesson_data['data']['activities']):
            lesson['classroom_id'] = course['classroom_id']

            # Lesson
            try:
                download_lesson_ppt(lesson, name_prefix + str(length - index))
            except Exception as e:
                print(e)
                print(f"Failed to download PPT for {name_prefix} - {lesson['title']}", file=sys.stderr)


# --- --- --- Section Download Lesson Video --- --- --- #

from video_processing import download_segments_in_parallel, concatenate_segments


def download_lesson_video(lesson: dict, name_prefix: str = ""):
    lesson_video_data = rainclassroom_sess.get(
        f"https://{YKT_HOST}/api/v3/lesson-summary/replay?lesson_id={lesson['courseware_id']}").json()


    name_prefix += "-" + lesson['title'].rstrip()
    # Remove illegal characters for Windows filenames
    name_prefix = re.sub(r'[<>:"\\|?*]', '_', name_prefix)

    if 'live' not in lesson_video_data['data']:
        print(f"v3 protocol detection failed, falling back to v1")

        fallback_flag = 1

        lesson_video_data = rainclassroom_sess.get(
            f"https://{YKT_HOST}/v/lesson/get_lesson_replay_timeline/?lesson_id={lesson['courseware_id']}").json()

        if 'live_timeline' not in lesson_video_data['data']:
            print(f"Skipping {name_prefix} - No Video", file=sys.stderr)
            return
    else:
        fallback_flag = 0

    if os.path.exists(f"{DOWNLOAD_FOLDER}/{name_prefix}.mp4"):
        print(f"Skipping {name_prefix} - Video already present")
        time.sleep(0.25)
        return

    has_error = False

    # Download segments in parallel
    try:
        download_segments_in_parallel(fallback_flag, CACHE_FOLDER, lesson_video_data, name_prefix)
    except Exception as e:
        print(e)
        print(f"Failed to download {name_prefix}", file=sys.stderr)
        has_error = True

    # Start concatenation if downloads were successful
    if not has_error:
        if 'live' in lesson_video_data['data'] and len(lesson_video_data['data']['live']) > 0:
            print(f"Concatenating {name_prefix}")
            concatenate_segments(CACHE_FOLDER, DOWNLOAD_FOLDER, name_prefix, len(lesson_video_data['data']['live']))
        elif 'live_timeline' in lesson_video_data['data'] and len(lesson_video_data['data']['live_timeline']) > 0:
            print(f"Concatenating {name_prefix}")
            concatenate_segments(CACHE_FOLDER, DOWNLOAD_FOLDER, name_prefix, len(lesson_video_data['data']['live_timeline']))
        else:
            print('concatenate cannot start due to previous failure')
    else:
        print('concatenate cannot start due to previous failure')

    if has_error:
        with open(f"{DOWNLOAD_FOLDER}/error.log", "a") as f:
            f.write(f"{name_prefix}\n")


from ppt_processing import download_ppt


def download_lesson_ppt(lesson: dict, name_prefix: str = ""):
    lesson_data = rainclassroom_sess.get(
        f"https://{YKT_HOST}/api/v3/lesson-summary/student?lesson_id={lesson['courseware_id']}").json()
    name_prefix += "-" + lesson['title'].rstrip()

    # Remove illegal characters for Windows filenames
    name_prefix = re.sub(r'[<>:"\\|?*]', '_', name_prefix)

    if 'presentations' not in lesson_data['data']:
        print(f"v3 protocol detection failed, falling back to v1")

        ppt_info = rainclassroom_sess.get(
            f"https://{YKT_HOST}/v2/api/web/lessonafter/{lesson['courseware_id']}/presentation?classroom_id={lesson['classroom_id']}").json()
        if 'id' not in ppt_info['data'][0]:
            print(f"Skipping {name_prefix} - No PPT", file=sys.stderr)
            return

        for index, ppt in enumerate(ppt_info['data']):
            # PPT
            try:
                ppt_raw_data = rainclassroom_sess.get(
                    f"https://{YKT_HOST}/v2/api/web/lessonafter/presentation/{ppt['id']}?classroom_id={lesson['classroom_id']}").json()
                download_ppt(1, args.ppt_problem_answer, args.ppt_to_pdf, CACHE_FOLDER, DOWNLOAD_FOLDER,
                             ppt_raw_data, name_prefix + f"-{index}")

            except Exception as e:
                print(e)
                print(f"Failed to download PPT {name_prefix} - {ppt['title']}", file=sys.stderr)

    else:
        for index, ppt in enumerate(lesson_data['data']['presentations']):
            # PPT
            try:
                ppt_raw_data = rainclassroom_sess.get(
                    f"https://{YKT_HOST}/api/v3/lesson-summary/student/presentation?presentation_id={ppt['id']}&lesson_id={lesson["courseware_id"]}").json()
                download_ppt(3,args.ppt_problem_answer, args.ppt_to_pdf, CACHE_FOLDER, DOWNLOAD_FOLDER,
                             ppt_raw_data, name_prefix + f"-{index}")

            except Exception as e:
                print(e)
                print(f"Failed to download PPT {name_prefix} - {ppt['title']}", file=sys.stderr)


# --- --- --- Section Main --- --- --- #


import option as opt

allin_flag = opt.ask_for_allin()

for course in courses:
    skip_flag = 0
    try:
        print(course)
        if not allin_flag:
            skip_flag = opt.ask_for_input()
            if skip_flag:
                continue
            else:
                get_lesson_list(course)
        else:
            get_lesson_list(course)
    except Exception as e:
        print(e)
        print(f"Failed to parse {course['name']}", file=sys.stderr)
