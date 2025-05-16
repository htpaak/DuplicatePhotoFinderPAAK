"""
파일 형식 정의 모듈

이 모듈은 프로그램에서 지원하는 모든 파일 형식을 정의합니다.
이미지, 비디오, 애니메이션 등의 형식을 집합(set) 또는 리스트(list)로 정의하여
코드의 일관성을 유지하고 중복을 방지합니다.
"""

# Pillow에서 일반적으로 지원하는 정적 이미지 형식
STATIC_IMAGE_FORMATS = {
    # 기본 형식
    '.png', '.jpg', '.jpeg', '.bmp',
    # 추가 형식
    '.tif', '.tiff', '.ico', '.pcx',
    '.ppm', '.pgm', '.pbm', '.tga',
}

# 프레임 검사가 필요한 포맷 (정적 이미지 또는 애니메이션일 수 있음)
FRAME_CHECK_FORMATS = {
    '.webp', '.gif', '.apng', '.mng'
}

# RAW 이미지 확장자
RAW_EXTENSIONS = {
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.rw2', '.orf',
    '.raf', '.pef', '.srw', '.kdc', '.raw'
}

# 항상 비디오/애니메이션으로 처리할 확장자
VIDEO_ONLY_EXTENSIONS = {
    # 일반 비디오 형식
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', 
    '.m4v', '.mpg', '.mpeg', '.3gp',
    # 항상 애니메이션으로 처리할 형식
    '.svg', '.ani', '.swf'
}

# 모든 이미지 형식 = 정적 이미지 + RAW 이미지 + 프레임 검사 필요 (실행 시 분류됨)
SUPPORTED_IMAGE_FORMATS = STATIC_IMAGE_FORMATS.union(RAW_EXTENSIONS).union(FRAME_CHECK_FORMATS)

# 비디오 및 애니메이션 확장자 (FRAME_CHECK_FORMATS는 실행 시 분류됨)
VIDEO_ANIMATION_EXTENSIONS = VIDEO_ONLY_EXTENSIONS.union(FRAME_CHECK_FORMATS)

# 지원하는 모든 파일 형식 (이미지 + 비디오 + 애니메이션)
ALL_SUPPORTED_FORMATS = STATIC_IMAGE_FORMATS.union(RAW_EXTENSIONS).union(VIDEO_ONLY_EXTENSIONS).union(FRAME_CHECK_FORMATS)

# 리스트 형태로도 제공 (일부 API에서 필요할 수 있음)
VIDEO_ANIMATION_EXTENSIONS_LIST = list(VIDEO_ANIMATION_EXTENSIONS)
ALL_SUPPORTED_FORMATS_LIST = list(ALL_SUPPORTED_FORMATS)

# 해시 유사도 임계값
HASH_THRESHOLD = 5
# 비디오 유사도 임계값 (상향 조정 - 더 엄격하게)
VIDEO_SIMILARITY_THRESHOLD = 92.0 