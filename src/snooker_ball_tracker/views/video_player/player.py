import typing

import numpy as np
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui
import PyQt5.QtWidgets as QtWidgets
from snooker_ball_tracker.ball_tracker import (ColourDetectionSettings,
                                               VideoPlayer)

from ..components import Ui_Label, Ui_PushButton


class Player(QtWidgets.QFrame):
    def __init__(self, video_player: VideoPlayer, colours: ColourDetectionSettings, 
                 videoFileOnClick: typing.Callable[[], typing.Any]):
        super().__init__()
        self.video_player = video_player
        self.colours = colours

        self.setSizePolicy(QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding))
        self.setMaximumWidth(self.video_player.width)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.selectVideoFile_btn = Ui_PushButton("Select Video File", parent=self, width=(200, 200))
        self.output_frame = Ui_Label("", parent=self)
        self.output_frame.mousePressEvent = self.output_frame_onclick

        self.selectVideoFile_btn.pressed.connect(videoFileOnClick)

        self.layout.addWidget(self.selectVideoFile_btn)
        self.video_player.output_frameChanged.connect(self.display_output_frame)

    def output_frame_onclick(self, event: QtGui.QMouseEvent):
        if self.colours.selected_colour != "NONE":
            x = event.pos().x()
            y = event.pos().y()

            pixels = self.video_player.hsv_frame[y-5:y+5, x-5:x+5]
            min_pixel = np.min(pixels, axis=0)[0]
            max_pixel = np.max(pixels, axis=0)[0]

            colour = {
                "LOWER": min_pixel,
                "UPPER": max_pixel
            }
            
            self.colours.colour_model.update(colour)

    def display_output_frame(self, output_frame):
        self.layout.removeWidget(self.selectVideoFile_btn)
        self.layout.addWidget(self.output_frame)
        self.setStyleSheet("background-color: black")
        output_frame = QtGui.QImage(output_frame.data, output_frame.shape[1], 
            output_frame.shape[0], QtGui.QImage.Format_RGB888).rgbSwapped()
        self.output_frame.setPixmap(QtGui.QPixmap.fromImage(output_frame))
