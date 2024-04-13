import os

def init():
    global DATA_DIR
    DATA_DIR = os.environ.get('XDG_DATA_HOME')
    global IMG_DIR
    IMG_DIR = f"{DATA_DIR}/images"

    if not os.path.exists(IMG_DIR):
        # shutil.rmtree(IMG_DIR)
        os.makedirs(IMG_DIR)

    print(DATA_DIR)
