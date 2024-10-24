import os
import sys

import argparse
import time

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
parser.add_argument("-c", "--session-cookie", help="Session Cookie", required=False)
parser.add_argument("-y", "--ykt-host", help="RainClassroom Host", required=False, default="pro.yuketang.cn")
parser.add_argument("--video", action="store_true", help="Download Video")
parser.add_argument("--ppt", action="store_true", help="Download PPT")
parser.add_argument("--ppt-to-pdf", action="store_true", help="Convert PPT to PDF", default=True)
parser.add_argument("--ppt-problem-answer", action="store_true", help="Store PPT Problem Answer", default=True)

args = parser.parse_args()

if args.help:
    print("""RainClassroom Video Downloader

requirements:
    - Python >= 3.12
    - requests
    - websocket-client
    - qrcode
    
required system binaries:
    - aria2c
    - ffmpeg with nvenc support
""")

    print(parser.format_help())

    exit()

import requests
import websocket
import json
import qrcode

# --- --- --- Section LOGIN --- --- --- #
# Login to RainClassroom
userinfo = {}
rainclassroom_sess = requests.session()

YKT_HOST = args.ykt_host
DOWNLOAD_FOLDER = "data"
CACHE_FOLDER = "cache"


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


if args.session_cookie is not None:
    rainclassroom_sess.cookies['sessionid'] = args.session_cookie

else:
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
    with open(f"{DOWNLOAD_FOLDER}/session.txt", "w") as f:
        f.write(rainclassroom_sess.cookies['sessionid'])


# --- --- --- Section Get Course List --- --- --- #

# 获取自己的课程列表
shown_courses = rainclassroom_sess.get(f"https://{YKT_HOST}/v2/api/web/courses/list?identity=2").json()

hidden_courses = rainclassroom_sess.get(f"https://{YKT_HOST}/v2/api/web/classroom_archive").json()

for course in hidden_courses['data']['classrooms']:
    course['classroom_id'] = course['id']

courses = shown_courses['data']['list'] + hidden_courses['data']['classrooms']

rainclassroom_sess.cookies['xtbz'] = 'ykt'


# --- --- --- Section Get Lesson List --- --- --- #
# {
#     "university_name": "",
#     "term": 202401,
#     "university_logo_pic": "",
#     "name": "NAME",
#     "type_count": [],
#     "students_count": 7,
#     "color_system": 3,
#     "course": {
#         "update_time": "",
#         "name": "",
#         "admin_id": 0,
#         "university_id": 0,
#         "type": 0,
#         "id": 0
#     },
#     "teacher": {
#         "user_id": 0,
#         "name": "",
#         "avatar": ""
#     },
#     "create_time": "",
#     "university_id": 0,
#     "time": "",
#     "course_id": 0,
#     "university_logo": "0",
#     "university_mini_logo": "0",
#     "id": 0,
#     "is_pro": true,
#     "color_code": 0
# }


def get_lesson_list(course: dict, name_prefix: str = ""):
    lesson_data = rainclassroom_sess.get(
        f"https://{YKT_HOST}/v2/api/web/logs/learn/{course['classroom_id']}?actype=14&page=0&offset=500&sort=-1").json()

    os.makedirs(f"{DOWNLOAD_FOLDER}/{course['name']}", exist_ok=True)
    os.makedirs(f"{CACHE_FOLDER}/{course['name']}", exist_ok=True)
    name_prefix += course['name'] + "/"

    l = len(lesson_data['data']['activities'])

    if args.video:
        for index, lesson in enumerate(lesson_data['data']['activities']):
            # Lesson
            try:
                download_lesson_video(lesson, name_prefix + str(l - index))
            except Exception as e:
                print(e)
                print(f"Failed to download video for {name_prefix} - {lesson['title']}", file=sys.stderr)

    if args.ppt:
        for index, lesson in enumerate(lesson_data['data']['activities']):
            # Lesson
            try:
                download_lesson_ppt(lesson, name_prefix + str(l - index))
            except Exception as e:
                print(e)
                print(f"Failed to download PPT for {name_prefix} - {lesson['title']}", file=sys.stderr)


# --- --- --- Section Download Lesson Video --- --- --- #
# {
#      "type": 14,
#      "id": 7153416,
#      "courseware_id": "909642544544463488",
#      "title": "R8-三相-周期非正弦",
#      "create_time": 1686274642000,
#      "attend_status": true,
#      "is_finished": true
# }


def download_lesson_video(lesson: dict, name_prefix: str = ""):
    lesson_video_data = rainclassroom_sess.get(
        f"https://{YKT_HOST}/api/v3/lesson-summary/replay?lesson_id={lesson['courseware_id']}").json()
    name_prefix += "-" + lesson['title']

    if 'live' not in lesson_video_data['data']:
        print(f"Skipping {name_prefix} - No Video", file=sys.stderr)
        return

    if os.path.exists(f"{DOWNLOAD_FOLDER}/{name_prefix}.mp4"):
        print(f"Skipping {name_prefix} - Video already present")
        return

    has_error = False

    for order, segment in enumerate(lesson_video_data['data']['live']):
        # Segment
        try:
            download_segment(segment['url'], order, name_prefix)
        except Exception as e:
            print(e)
            print(f"Failed to download {name_prefix} - {segment['order']}", file=sys.stderr)
            has_error = True

    if not has_error and len(lesson_video_data['data']['live']) > 0:
        print(f"Concatenating {name_prefix}")

        with open(f"{CACHE_FOLDER}/concat.txt", "w") as f:
            f.write("\n".join(
                [f"file '{name_prefix}-{i}.mp4'" for i in range(len(lesson_video_data['data']['live']))]
            ))

        cmd = f"ffmpeg -f concat -safe 0 -hwaccel cuda -hwaccel_output_format cuda -i {CACHE_FOLDER}/concat.txt -c:v hevc_nvenc -b:v 200k -maxrate 400k -bufsize 3200k -r 8 -rc-lookahead 1024 -c:a copy -rematrix_maxval 1.0 -ac 1 '{DOWNLOAD_FOLDER}/{name_prefix}.mp4' -n"

        print(cmd)
        os.system(cmd)

    if has_error:
        with open(f"{DOWNLOAD_FOLDER}/error.log", "a") as f:
            f.write(f"{name_prefix}\n")


# --- --- --- Section Download Segment --- --- --- #
# {
#     "id": "743834725938342272",
#     "code": "kszt_DdQU9sOod7o",
#     "type": 2,
#     "source": "th",
#     "url": "https://kszt-playback.xuetangx.com/gifshow-xuetangx/73466bdb387702307504996781/f0.mp4?auth_key=1729778852-4128559473511008914-0-e0c959d1504f92ef5a5d45000f46330d",
#     "start": 1666508813000,
#     "end": 1666510612000,
#     "duration": 1799000,
#     "hiddenStatus": 0,
#     "order": 0,
#     "replayOssStatus": 0,
#     "recordFileId": "",
#     "recordType": "",
#     "subtitlePath": ""
# }


def download_segment(url: str, order: int, name_prefix: str = ""):
    print(f"Downloading {name_prefix} - {order}")
    ret = os.system(
        f"aria2c -o '{CACHE_FOLDER}/{name_prefix}-{order}.mp4' -x 16 -s 16 '{url}' -c")
    if ret != 0:
        raise Exception(f"Failed to download {name_prefix}-{order}")

# --- --- --- Section Download Lesson PPT --- --- --- #
# {
#     "code": 0,
#     "msg": "OK",
#     "data": {
#         "lesson": {
#             "id": "1267751345493205504",
#             "title": "计算机网络原理  课堂提问（2）",
#             "startTime": 1728964537223,
#             "endTime": 1728965834350,
#             "teacherIdentityId": "15753469",
#             "classroom": {
#                 "id": "3134428",
#                 "name": "2024秋-计算机网络原理-2",
#                 "pro": true
#             },
#             "course": {
#                 "id": "1360043",
#                 "name": "计算机网络原理"
#             }
#         },
#         "fileSharing": {
#             "count": 0,
#             "cover": null
#         },
#         "teacher": {
#             "identityId": "15753469",
#             "avatar": "0",
#             "name": "徐明伟",
#             "number": "1998990267"
#         },
#         "replayType": 0,
#         "replayOssStatus": 0,
#         "presentations": [
#             {
#                 "id": "1267751453966295552",
#                 "title": "计算机网络原理  课堂提问",
#                 "cover": "https://thu-private-qn.yuketang.cn/slide/11789532/cover435_20241015115349.jpg?e=1729790227&token=IAM-gs8ue1pDIGwtR1CR0Zjdagg7Q2tn5G_1BqTmhmqa:CkT5RMnhXFxcVUWoxVU2xxjA6ac=",
#                 "slidesCount": 21,
#                 "totalSlidesCount": 59,
#                 "doubtCount": 0,
#                 "collectCount": 0,
#                 "conf": "{\"show_presentation\":\"film\",\"slides\":[\"1267751453966295553\",\"1267751453974684160\",\"1267751453974684162\",\"1267751453974684164\",\"1267751453983072768\",\"1267751453983072770\",\"1267751453983072772\",\"1267751453983072774\",\"1267751453991461376\",\"1267751453991461378\",\"1267751453991461379\",\"1267751453999849984\",\"1267751453999849985\",\"1267751453999849986\",\"1267751453999849987\",\"1267751454008238592\",\"1267751454008238593\",\"1267751454008238594\",\"1267751454008238595\",\"1267751454016627200\",\"1267751454016627201\"],\"hide_slides\":[]}"
#             }
#         ],
#         "user": {
#             "identityId": "21640720",
#             "avatar": "http://qn-sx.yuketang.cn/tougao_pic_AFzVVZcN5p9.png",
#             "name": "董业恺",
#             "number": "2022010426"
#         },
#         "activityId": "7970721",
#         "memoContent": "",
#         "liveViewed": false,
#         "doubtSlides": [],
#         "collectSlides": [],
#         "checkIn": {
#             "lessonId": "1267751345493205504",
#             "identityId": "21640720",
#             "score": 1000,
#             "source": 5,
#             "time": 1728964549329,
#             "valid": 1,
#             "problemScore": 1000,
#             "quizScore": -1,
#             "duration": 0,
#             "addScore": null,
#             "redEnvelope": 0,
#             "correctCount": 10,
#             "incorrectCount": 4,
#             "unMarkCount": 0
#         },
#         "quizzes": [],
#         "danmuList": [],
#         "tougaoList": [],
#         "toastType": 0,
#         "problems": [
#             {
#                 "problemId": "1267751453974684162",
#                 "problemType": 1,
#                 "problemScore": 100,
#                 "index": 3,
#                 "cover": "https://thu-private-qn.yuketang.cn/slide/11789532/cover433_20241015115349.jpg?e=1729790227&token=IAM-gs8ue1pDIGwtR1CR0Zjdagg7Q2tn5G_1BqTmhmqa:hLi2EEWUQHgVeKyP9y4bi7neaYQ=",
#                 "presentationId": "1267751453966295552",
#                 "answer": [
#                     "D"
#                 ],
#                 "ans_type": "",
#                 "comment": {},
#                 "correctAnswer": [
#                     "D"
#                 ],
#                 "score": 100,
#                 "submitTime": 1728964586371,
#                 "scoreTime": 0,
#                 "correct": true,
#                 "blankStatus": [],
#                 "anonymous": null,
#                 "remarkDetail": {},
#                 "teamInfo": null
#             }
#         ]
#     }
# }


def download_lesson_ppt(lesson: dict, name_prefix: str = ""):
    lesson_data = rainclassroom_sess.get(f"https://{YKT_HOST}/api/v3/lesson-summary/student?lesson_id={lesson['courseware_id']}").json()
    name_prefix += "-" + lesson['title']

    if 'presentations' not in lesson_data['data']:
        print(f"Skipping {name_prefix} - No PPT", file=sys.stderr)
        return

    for index, ppt in enumerate(lesson_data['data']['presentations']):
        # PPT
        try:
            download_ppt(lesson["courseware_id"], ppt['id'], name_prefix + f"-{index}")
        except Exception as e:
            print(e)
            print(f"Failed to download PPT {name_prefix} - {ppt['title']}", file=sys.stderr)

# --- --- --- Section Download PPT --- --- --- #
# {
#     "code": 0,
#     "msg": "OK",
#     "data": {
#         "presentation": {
#             "id": "714674183600571776",
#             "title": "L1_课程介绍",
#             "cover": "https://qn-st0.yuketang.cn/FudgWS2XoU3bXLxReeSBBhYTWJsX",
#             "width": 720,
#             "height": 540,
#             "conf": {
#                 "show_presentation": "all",
#                 "slides": [
#                     "714674183617348992"
#                 ],
#                 "hide_slides": []
#             }
#         },
#         "slides": [
#             {
#                 "id": "714674183617348992",
#                 "index": 1,
#                 "doubtCount": 0,
#                 "collectCount": 0,
#                 "cover": "https://qn-st0.yuketang.cn/FudgWS2XoU3bXLxReeSBBhYTWJsX",
#                 "problem": null,
#                 "result": null
#             }
#         ]
#     }
# }


def download_ppt(lesson_id: str, ppt_id: str, name_prefix: str = ""):
    print(f"Downloading {name_prefix}")
    ppt_raw_data = rainclassroom_sess.get(f"https://{YKT_HOST}/api/v3/lesson-summary/student/presentation?presentation_id={ppt_id}&lesson_id={lesson_id}").json()
    name_prefix += "-" + ppt_raw_data['data']['presentation']['title']

    # If PDF is present, skip
    if os.path.exists(f"{DOWNLOAD_FOLDER}/{name_prefix}.pdf"):
        print(f"Skipping {name_prefix} - PDF already present")
        return

    os.makedirs(f"{DOWNLOAD_FOLDER}/{name_prefix}", exist_ok=True)

    images = []

    with open(f"{CACHE_FOLDER}/ppt_download.txt", "w") as f:
        for slide in ppt_raw_data['data']['slides']:
            f.write(f"{slide['cover']}\n out={DOWNLOAD_FOLDER}/{name_prefix}/{slide['index']}.jpg\n")
            images.append(f"{DOWNLOAD_FOLDER}/{name_prefix}/{slide['index']}.jpg")

        # if os.path.exists(f"{DOWNLOAD_FOLDER}/{name_prefix}/{slide['index']}.jpg"):
        #     print(f"Skipping {name_prefix} - {slide['index']}")
        #     continue
        #
        # with open(f"{DOWNLOAD_FOLDER}/{name_prefix}/{slide['index']}.jpg", "wb") as f:
        #     f.write(requests.get(slide['cover']).content)

    os.system(f"aria2c -i {CACHE_FOLDER}/ppt_download.txt -x 16 -s 16 -c")

    from PIL import Image

    if args.ppt_problem_answer:
        from PIL import ImageDraw, ImageFont

        for problem in ppt_raw_data['data']['slides']:
            if problem['problem'] is None:
                continue

            answer = "Answer: " + "; ".join(problem['problem']['content']['answer'])

            image = Image.open(f"{DOWNLOAD_FOLDER}/{name_prefix}/{problem['index']}.jpg")

            draw = ImageDraw.Draw(image)

            # Load the font
            font = ImageFont.load_default(size=40)
            text_bbox = draw.textbbox(xy=(20, 20), text=answer, font=font)

            # Add semi-transparent black rectangle
            draw.rectangle([text_bbox[0] - 10, text_bbox[1] - 10, text_bbox[2] + 10, text_bbox[3] + 10], fill="#bbb")

            # Draw the text on top (white)
            draw.text((text_bbox[0], text_bbox[1]), answer, anchor="lt", font=font, fill="#333")

            image.convert(mode="RGB").save(f"{DOWNLOAD_FOLDER}/{name_prefix}/{problem['index']}-ans.jpg")

            # Replace the image in the list
            images[images.index(f"{DOWNLOAD_FOLDER}/{name_prefix}/{problem['index']}.jpg")] = f"{DOWNLOAD_FOLDER}/{name_prefix}/{problem['index']}-ans.jpg"

            print(f"Added Answer to {name_prefix} - {problem['index']}")

    if not args.ppt_to_pdf:
        return

    print(f"Converting {name_prefix}")

    images = [Image.open(i) for i in images]
    images[0].save(f"{DOWNLOAD_FOLDER}/{name_prefix}.pdf", "PDF", resolution=100.0, save_all=True, append_images=images[1:])


# --- --- --- Section Main --- --- --- #


for course in courses:
    try:
        get_lesson_list(course)
    except Exception as e:
        print(e)
        print(f"Failed to parse {course['name']}", file=sys.stderr)
