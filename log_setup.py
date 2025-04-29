import os
import sys
import logging

class TeeStream:
    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None] # None이 아닌 스트림만 저장

    def write(self, message):
        for stream in self.streams:
            # 각 스트림에 쓰기 전에 None 여부 확인 (이중 확인, 생성자에서 이미 처리)
            if stream:
                try:
                    stream.write(message)
                    stream.flush()
                except Exception as e:
                    # 스트림 쓰기 오류 발생 시 예외 처리 (선택적)
                    # print(f"Error writing to stream {stream}: {e}")
                    pass # 오류 발생 시 조용히 넘어감

    def flush(self):
        for stream in self.streams:
            if stream: # None 체크 추가
                try:
                    stream.flush()
                except Exception as e:
                    # print(f"Error flushing stream {stream}: {e}")
                    pass

def setup_logging():
    # --- 조건부 로깅 비활성화 ---
    # PyInstaller로 패키징되었고(--windowed 추정, sys.stdout이 None) 로그 비활성화
    is_frozen = getattr(sys, 'frozen', False)
    is_windowed = sys.stdout is None

    if is_frozen and is_windowed:
        # 로깅을 완전히 비활성화하고 아무것도 하지 않음
        # logging.disable(logging.CRITICAL + 1) # 필요하다면 로깅 호출 자체를 막을 수도 있음
        print("Windowed frozen app detected, disabling file logging.") # 디버깅용 출력(실제로는 안 보임)
        return # 로깅 설정 건너뛰기
    # --- 조건부 로깅 비활성화 끝 ---

    # logs 디렉토리 생성
    os.makedirs("logs", exist_ok=True)
    log_file_path = os.path.abspath("logs/debug.log")

    # 로그 파일 열기 (덮어쓰기)
    log_file = open(log_file_path, mode='w', encoding='utf-8')

    # stdout, stderr 를 TeeStream으로 교체 (터미널 + 파일 모두 출력)
    # 원본 스트림이 None일 경우 TeeStream에 포함시키지 않음
    sys.stdout = TeeStream(sys.__stdout__, log_file)
    sys.stderr = TeeStream(sys.__stderr__, log_file)

    # logging 설정
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout  # stdout도 이미 TeeStream이므로 파일+터미널로 감
    )

    logging.debug("Logging initialized.")
