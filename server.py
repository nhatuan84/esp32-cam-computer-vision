from aiohttp import web
import aiohttp
import threading
import queue
import numpy as np
import cv2
import jinja2
import aiohttp_jinja2
import os
import asyncio
import base64


cams_queue = queue.Queue(maxsize=10)
monitor_queue = []

face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
eyes_cascade = cv2.CascadeClassifier('haarcascade_eye_tree_eyeglasses.xml')

def cv2_processing(frame):
    try:
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame_gray = cv2.equalizeHist(frame_gray)
        #-- Detect faces
        faces = face_cascade.detectMultiScale(frame_gray)
        for (x,y,w,h) in faces:
            center = (x + w//2, y + h//2)
            frame = cv2.ellipse(frame, center, (w//2, h//2), 0, 0, 360, (255, 0, 255), 4)
            faceROI = frame_gray[y:y+h,x:x+w]
            #-- In each face, detect eyes
            eyes = eyes_cascade.detectMultiScale(faceROI)
            for (x2,y2,w2,h2) in eyes:
                eye_center = (x + x2 + w2//2, y + y2 + h2//2)
                radius = int(round((w2 + h2)*0.25))
                frame = cv2.circle(frame, eye_center, radius, (255, 0, 0 ), 4)
    except:
        pass
    return frame


def handle_cams(cams_queue, monitor_queue):
    loop = asyncio.new_event_loop()
    mons = []
    

    while True:
        if not cams_queue.empty():
            cam = cams_queue.get()
            cam_id = cam[0]
            image_bytes = np.array(cam[1]).tobytes()
            image_bytes = np.frombuffer(image_bytes, dtype=np.uint8) 
            img = cv2.imdecode(image_bytes, flags=cv2.IMREAD_COLOR)
            img = cv2_processing(img)
            retval, buffer = cv2.imencode('.jpg', img)
            jpg_as_text = base64.b64encode(buffer).decode("utf-8")
            for ws in monitor_queue:
                try:
                    loop.run_until_complete(ws.send_str(jpg_as_text))
                except:
                    print('websocket closed')
            #cv2.imshow('abc', img)
            #cv2.waitKey(0)
            #cv2.imwrite('tuan.jpg', img)


async def websocket_cam_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    data = []
    cam_id = None
    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data.startswith('start'):
                cam_id = msg.data.replace('start:', '')
                data = []
            elif msg.data == 'end':
                cams_queue.put([cam_id, data])
        elif msg.type == aiohttp.WSMsgType.BINARY:
            data.append(msg.data)
        elif msg.type == aiohttp.WSMsgType.ERROR:
            await ws.close()
            print(ws.exception())
    return ws

async def monitor_cam_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    monitor_queue.append(ws)
    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data == 'close':
                await ws.close()
        elif msg.type == aiohttp.WSMsgType.ERROR:
            await ws.close()
            print(ws.exception())
    return ws

@aiohttp_jinja2.template("index.html")
async def index(request):
    return {}


if __name__ == '__main__':
    p = threading.Thread(target=handle_cams, args=((cams_queue, monitor_queue)))
    p.start()

    app = web.Application()
    aiohttp_jinja2.setup(
        app, loader=jinja2.FileSystemLoader(os.path.join(os.getcwd(), "templates"))
    )
    app.router.add_get('/', index, name="index")
    app.router.add_get('/ws', websocket_cam_handler)
    app.router.add_get('/monitor', monitor_cam_handler)

    web.run_app(app)
