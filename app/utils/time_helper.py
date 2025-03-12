from datetime import time

def is_open_now(open_time: time, close_time: time, check_time: time) -> bool:
    """
    簡易判斷 check_time 是否在 open_time <= x <= close_time 之間
    未處理跨午夜。若要跨午夜，可擴充。
    """
    return open_time <= check_time <= close_time