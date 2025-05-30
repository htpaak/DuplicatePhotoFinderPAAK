import os
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPixmap, QResizeEvent, QImage, QPainter, QIcon, QColor, QFont, QPen, QPolygon
from PyQt5.QtCore import Qt, QSize, QRect, QPoint
from typing import Optional
from PIL import Image
import rawpy
import numpy as np
from supported_formats import RAW_EXTENSIONS, VIDEO_ONLY_EXTENSIONS, FRAME_CHECK_FORMATS
import av  # PyAV 임포트 추가

class ImageLabel(QLabel):
    """동적 크기 조절 및 비율 유지를 지원하는 이미지 레이블"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_pixmap: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter) # 기본 정렬 설정
        self.setMinimumSize(100, 100) # 최소 크기 설정 (예시)
        self.setObjectName("ImageLabel") # 스타일시트 적용 위한 객체 이름
        self.is_video = False # 비디오 파일인지 여부

    def load_path(self, file_path: str) -> bool:
        """파일 경로를 로드하고 결과를 반환합니다. 편의 메서드입니다."""
        return self.setPixmapFromFile(file_path)

    def setPixmapFromFile(self, file_path: str) -> bool:
        """파일 경로로부터 Pixmap을 로드하고 원본을 저장합니다. RAW, TGA 및 비디오 파일 지원."""
        if not file_path or not os.path.exists(file_path):
            self._original_pixmap = None
            self.setText("File Not Found")
            return False

        pixmap = None
        file_ext = os.path.splitext(file_path)[1].lower()
        # 비디오/애니메이션 파일 확인 (두 집합 모두 확인)
        self.is_video = file_ext in VIDEO_ONLY_EXTENSIONS or file_ext in FRAME_CHECK_FORMATS

        try:
            # 비디오 파일 처리
            if self.is_video:
                # WebP 애니메이션 특별 처리
                webp_processed = False
                if file_ext == '.webp':
                    try:
                        # Pillow로 WebP 애니메이션 첫 프레임 추출
                        with Image.open(file_path) as img:
                            # 첫 프레임 사용
                            img.seek(0)
                            # PIL Image를 QPixmap으로 변환
                            if img.mode == "RGBA":
                                img_data = img.tobytes("raw", "RGBA")
                                qimg = QImage(img_data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888)
                            else:
                                rgb_img = img.convert("RGB")
                                img_data = rgb_img.tobytes("raw", "RGB")
                                qimg = QImage(img_data, rgb_img.width, rgb_img.height, rgb_img.width * 3, QImage.Format_RGB888)
                                if rgb_img != img:
                                    rgb_img.close()
                            
                            if not qimg.isNull():
                                pixmap = QPixmap.fromImage(qimg)
                                if not pixmap.isNull():
                                    # "Animation" 텍스트 추가
                                    painter = QPainter(pixmap)
                                    painter.setRenderHint(QPainter.Antialiasing)
                                    painter.setPen(QPen(QColor(255, 255, 255, 200)))
                                    painter.setFont(QFont("Arial", 12, QFont.Bold))
                                    
                                    # 반투명 배경 추가
                                    bg_rect = QRect(0, 0, pixmap.width(), 30)
                                    painter.fillRect(bg_rect, QColor(0, 0, 0, 150))
                                    
                                    # "WebP Animation" 텍스트 추가
                                    painter.drawText(bg_rect, Qt.AlignCenter, "WebP Animation")
                                    painter.end()
                                    webp_processed = True  # 성공적으로 처리됨
                    except Exception as webp_err:
                        print(f"WebP 애니메이션 처리 오류, 일반 비디오 처리로 전환: {webp_err}")
                        # 오류 발생 시 일반 비디오 처리로 계속 진행
                
                # 일반 비디오 처리 (WebP가 성공적으로 처리되지 않은 경우)
                if not webp_processed:
                    # PyAV를 사용하여 첫 프레임 추출 시도
                    try:
                        # 첫 프레임 추출 시도
                        frame_extracted = False
                        container = av.open(file_path)
                        video_stream = next((s for s in container.streams if s.type == 'video'), None)
                        
                        if video_stream:
                            # 첫 번째 키프레임을 찾아 추출
                            container.seek(0)
                            for frame in container.decode(video_stream):
                                # 프레임을 PIL 이미지로 변환
                                pil_img = frame.to_image()
                                # PIL 이미지를 QPixmap으로 변환
                                img_bytes = pil_img.tobytes('raw', 'RGB')
                                qimg = QImage(img_bytes, pil_img.width, pil_img.height, 
                                            pil_img.width * 3, QImage.Format_RGB888)
                                pixmap = QPixmap.fromImage(qimg)
                                frame_extracted = True
                                break  # 첫 프레임만 사용
                        
                        container.close()
                        
                        # 프레임 추출 실패 시 기본 비디오 아이콘 사용
                        if not frame_extracted:
                            raise Exception("첫 프레임 추출 실패")
                            
                    except Exception as e:
                        print(f"비디오 프레임 추출 오류: {e}")
                        # 추출 실패 시 기본 비디오 아이콘 사용
                        video_icon = QPixmap(300, 300)
                        video_icon.fill(Qt.black)  # 배경을 검은색으로 변경
                        
                        # 비디오 아이콘 그리기
                        painter = QPainter(video_icon)
                        painter.setRenderHint(QPainter.Antialiasing)
                        
                        # 비디오 아이콘 중앙에 텍스트 그리기
                        painter.setPen(QPen(QColor(255, 255, 255)))  # 흰색 텍스트
                        font = QFont("Arial", 20, QFont.Bold)
                        painter.setFont(font)
                        
                        # 파일명 표시 (너무 길면 줄임)
                        basename = os.path.basename(file_path)
                        if len(basename) > 20:
                            basename = basename[:17] + "..."
                            
                        # 비디오 표시 추가
                        rect = QRect(10, 10, 280, 280)
                        painter.drawText(rect, Qt.AlignCenter, f"VIDEO\n{basename}")
                        
                        # 프레임 그리기 (화면 비율 표현)
                        painter.setPen(QPen(QColor(255, 255, 255), 3))
                        frame_rect = QRect(50, 80, 200, 140)  # 화면 비율을 16:9로 표현
                        painter.drawRect(frame_rect)
                        
                        # 재생 버튼 그리기
                        painter.setBrush(QColor(255, 255, 255))
                        # QPolygon 생성하여 점 좌표 추가
                        play_triangle = QPolygon()
                        play_triangle.append(QPoint(frame_rect.center().x() - 15, frame_rect.center().y() - 25))
                        play_triangle.append(QPoint(frame_rect.center().x() - 15, frame_rect.center().y() + 25))
                        play_triangle.append(QPoint(frame_rect.center().x() + 30, frame_rect.center().y()))
                        painter.drawPolygon(play_triangle)
                        
                        painter.end()
                        pixmap = video_icon
                    
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