environment:
    conda env create -f conda_environment.yml

    
requirements:
    - Python >= 3.12
    - requests
    - websocket-client (qrcode login)
    - qrcode (qrcode login)
    - Pillow (Add answer to problem; Convert PPT to PDF)

required system binaries:
    - aria2c (Download files multi-threaded & resume support)
    - ffmpeg with nvenc support (Concatenate video segments and convert to HEVC)
""")

usage: main_windows.py [-h] [-c SESSION_COOKIE] [-y YKT_HOST] [--video] [--ppt] [--ppt-to-pdf] [--ppt-problem-answer]
                       [--course-name-filter COURSE_NAME_FILTER] [--lesson-name-filter LESSON_NAME_FILTER]

options:
  -h, --help            Show this help message and exit
  -c SESSION_COOKIE, --session-cookie SESSION_COOKIE
                        Session Cookie
  -y YKT_HOST, --ykt-host YKT_HOST
                        RainClassroom Host
  --video               Download Video
  --ppt                 Download PPT
  --ppt-to-pdf          Convert PPT to PDF
  --ppt-problem-answer  Store PPT Problem Answer
  --course-name-filter COURSE_NAME_FILTER
                        Filter Course Name
  --lesson-name-filter LESSON_NAME_FILTER
                        Filter Lesson Name
