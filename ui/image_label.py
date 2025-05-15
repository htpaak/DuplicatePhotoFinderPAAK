import os
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPixmap, QResizeEvent, QImage, QPainter, QIcon
from PyQt5.QtCore import Qt, QSize
from typing import Optional
from PIL import Image
import rawpy
import numpy as np
from image_processor import RAW_EXTENSIONS, VIDEO_EXTENSIONS

class ImageLabel(QLabel):
    """동적 크기 조절 및 비율 유지를 지원하는 이미지 레이블"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_pixmap: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter) # 기본 정렬 설정
        self.setMinimumSize(100, 100) # 최소 크기 설정 (예시)
        self.setObjectName("ImageLabel") # 스타일시트 적용 위한 객체 이름
        self.is_video = False # 비디오 파일인지 여부

    def setPixmapFromFile(self, file_path: str) -> bool:
        """파일 경로로부터 Pixmap을 로드하고 원본을 저장합니다. RAW, TGA 및 비디오 파일 지원."""
        if not file_path or not os.path.exists(file_path):
            self._original_pixmap = None
            self.setText("File Not Found")
            return False

        pixmap = None
        file_ext = os.path.splitext(file_path)[1].lower()
        self.is_video = file_ext in VIDEO_EXTENSIONS # 비디오 파일 여부 저장

        try:
            # 비디오 파일 처리
            if self.is_video:
                # 비디오용 기본 아이콘 또는 썸네일 표시
                try:
                    # PyAV를 사용하여 첫 프레임 추출 시도 (여기서는 아이콘으로 대체)
                    video_icon = QPixmap(300, 300) # 빈 pixmap 생성
                    video_icon.fill(Qt.transparent) # 배경 투명하게
                    
                    # 기본 비디오 아이콘 그리기
                    painter = QPainter(video_icon)
                    painter.setRenderHint(QPainter.Antialiasing)
                    
                    # 비디오 아이콘 중앙에 그리기
                    icon = QIcon.fromTheme("video-x-generic")
                    if icon.isNull():
                        # 테마 아이콘이 없으면 텍스트로 대체
                        painter.setPen(Qt.white)
                        painter.drawText(video_icon.rect(), Qt.AlignCenter, "VIDEO")
                    else:
                        icon.paint(painter, video_icon.rect())
                    
                    painter.end()
                    pixmap = video_icon
                    
                    # 파일명 표시
                    self.setText(f"VIDEO: {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"비디오 아이콘 생성 오류: {e}")
                    self.setText(f"VIDEO FILE\n{os.path.basename(file_path)}")
                    return False
                
            # RAW 또는 TGA 파일 처리
            elif file_ext in RAW_EXTENSIONS or file_ext == '.tga':
                img_pil = None
                raw_obj = None
                qimage = None # QImage 객체 초기화
                try:
                    if file_ext in RAW_EXTENSIONS:
                        raw_obj = rawpy.imread(file_path)
                        rgb_array = raw_obj.postprocess(use_camera_wb=True)
                        img_pil = Image.fromarray(rgb_array)
                    elif file_ext == '.tga':
                        img_pil = Image.open(file_path)

                    if img_pil:
                        # PIL Image -> QImage 직접 변환
                        img_pil.draft(None, None) # Ensure image data is loaded
                        if img_pil.mode == "RGBA":
                            bytes_per_line = img_pil.width * 4
                            qimage = QImage(img_pil.tobytes("raw", "RGBA"), img_pil.width, img_pil.height, bytes_per_line, QImage.Format_RGBA8888)
                        elif img_pil.mode == "RGB":
                            bytes_per_line = img_pil.width * 3
                            qimage = QImage(img_pil.tobytes("raw", "RGB"), img_pil.width, img_pil.height, bytes_per_line, QImage.Format_RGB888)
                        else:
                            # 다른 모드는 RGB로 변환 시도
                            try:
                                rgb_img = img_pil.convert("RGB")
                                bytes_per_line = rgb_img.width * 3
                                qimage = QImage(rgb_img.tobytes("raw", "RGB"), rgb_img.width, rgb_img.height, bytes_per_line, QImage.Format_RGB888)
                                rgb_img.close() # 변환된 이미지 닫기
                            except Exception as convert_err:
                                print(f"Could not convert PIL image mode {img_pil.mode} to RGB for {file_path}: {convert_err}")
                                self.setText(f"Unsupported Image Mode\n{os.path.basename(file_path)}")
                                return False

                        if qimage and not qimage.isNull():
                            pixmap = QPixmap.fromImage(qimage)
                        else:
                             print(f"Failed to create QImage from PIL data for {file_path}")
                             self.setText(f"QImage Creation Failed\n{os.path.basename(file_path)}")
                             return False

                except rawpy.LibRawIOError as e:
                    print(f"rawpy I/O error for {file_path}: {e}")
                    self.setText(f"RAW Load Error (I/O)\n{os.path.basename(file_path)}")
                    return False
                except Exception as e:
                    print(f"Error processing {file_ext} file {file_path}: {e}")
                    self.setText(f"Cannot Load Image\n{os.path.basename(file_path)}")
                    return False
                finally:
                    if raw_obj:
                        raw_obj.close()
                    if img_pil and hasattr(img_pil, 'close'):
                         try:
                             img_pil.close()
                         except Exception as close_err:
                              print(f"Error closing PIL image {file_path}: {close_err}")

            # 기타 지원 형식 (Qt/Pillow 기본 로더 사용)
            else:
                pixmap = QPixmap(file_path)

            # Pixmap 유효성 검사 및 저장
            if pixmap and not pixmap.isNull():
                self._original_pixmap = pixmap
                self.updatePixmap()
                return True
            else:
                self._original_pixmap = None
                # pixmap 생성 실패 메시지는 위에서 처리됨
                if not (file_ext in RAW_EXTENSIONS or file_ext == '.tga' or self.is_video): # 일반 파일 로드 실패 시 메시지 설정
                     self.setText(f"Invalid Image File\n{os.path.basename(file_path)}")
                return False

        except Exception as e:
            print(f"Unexpected error in setPixmapFromFile for {file_path}: {e}")
            self._original_pixmap = None
            self.setText(f"Load Error\n{os.path.basename(file_path)}")
            return False

    def updatePixmap(self):
        """원본 Pixmap을 현재 레이블 크기에 맞게 스케일링하여 표시합니다."""
        if not self._original_pixmap:
            self.clear()
            # 필요 시 기본 텍스트 설정
            # self.setText("Image Area")
            return

        # 현재 레이블 크기 가져오기
        label_size = self.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            # 위젯 크기가 유효하지 않으면 스케일링 건너뛰기
             super().setPixmap(self._original_pixmap)
             return

        # 원본 비율 유지하며 스케일링
        scaled_pixmap = self._original_pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        super().setPixmap(scaled_pixmap) # QLabel의 setPixmap 직접 호출

    def resizeEvent(self, event: QResizeEvent):
        """위젯 크기가 변경될 때 호출됩니다."""
        self.updatePixmap() # 크기 변경 시 이미지 업데이트
        super().resizeEvent(event)

    def clear(self):
        """이미지와 원본 Pixmap을 초기화합니다."""
        self._original_pixmap = None
        self.is_video = False
        super().clear()
        self.setText("Image Area") # 초기 텍스트 설정 