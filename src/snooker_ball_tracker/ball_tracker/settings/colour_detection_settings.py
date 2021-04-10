from collections import OrderedDict
from copy import deepcopy

import numpy as np
import PyQt5.QtCore as QtCore
import snooker_ball_tracker.settings as s

from .hsv_colour import HSVColour


class ColourDetectionSettings(QtCore.QObject):
    def __init__(self):
        """Creates and instance of this class that contains colour detection
        properties used by the ball tracker"""
        super().__init__()
        self._colours = deepcopy(s.COLOURS)
        self._colour_model = HSVColour()
        self._colour_mask = False
        self._selected_colour = "NONE"

        self._colour_model.l_HueChanged.connect(lambda value: self.update_colour_value("LOWER", 0, value))
        self._colour_model.l_SaturationChanged.connect(lambda value: self.update_colour_value("LOWER", 1, value))
        self._colour_model.l_ValueChanged.connect(lambda value: self.update_colour_value("LOWER", 2, value))
        self._colour_model.u_HueChanged.connect(lambda value: self.update_colour_value("UPPER", 0, value))
        self._colour_model.u_SaturationChanged.connect(lambda value: self.update_colour_value("UPPER", 1, value))
        self._colour_model.u_ValueChanged.connect(lambda value: self.update_colour_value("UPPER", 2, value))

    @property
    def colours(self) -> dict:
        """Copy of colour values loaded from settings

        :return: colours
        :rtype: dict
        """
        return self._colours

    @colours.setter
    def colours(self, value: dict):
        """Colours setter

        :param value: value to set
        :type value: dict
        """
        self._colours = value
        if self._selected_colour != "NONE":
            self.colour_model.update(self._colours[self._selected_colour])

    @property
    def colour_model(self) -> HSVColour:
        """Colour model used to store temporary values in sliders

        :return: colour model
        :rtype: HSVColourModel
        """
        return self._colour_model

    @property
    def colour_mask(self) -> bool:
        """Mask selected colour in frames if True

        :return: colour mask
        :rtype: bool
        """
        return self._colour_mask

    colour_maskChanged = QtCore.pyqtSignal(bool)

    @colour_mask.setter
    def colour_mask(self, value: bool):
        """Colour mask setter

        :param value: value to set
        :type value: bool
        """
        self._colour_mask = value
        self.colour_maskChanged.emit(self._colour_mask)

    @property
    def selected_colour(self) -> str:
        """Selected colour that we are currently detecting in frames

        :return: selected colour
        :rtype: str
        """
        return self._selected_colour

    selected_colourChanged = QtCore.pyqtSignal(str)

    @selected_colour.setter
    def selected_colour(self, value: str):
        """Selected colour setter

        :param value: value to set
        :type value: str
        """
        self._selected_colour = value.upper()

        if self._selected_colour != "NONE":
            self._colour_model.update(self._colours[self._selected_colour])
        else:
            self._colour_model.clear()

        self.selected_colourChanged.emit(self._selected_colour)

    def update_colour_value(self, _range: str, index: int, value: int):
        """Update specific colour range value

        :param _range: either `LOWER` or `UPPER`
        :type _range: str
        :param index: index from 0 to 2
        :type index: int
        :param value: value to set to colour value
        :type value: int
        """
        self._colours[self._selected_colour][_range][index] = value

    def reset(self):
        """Reset selected colour in `colours` and `colour_model` with original values from settings"""
        if self._selected_colour != "NONE":
            self._colour_model.update(s.COLOURS[self._selected_colour])
