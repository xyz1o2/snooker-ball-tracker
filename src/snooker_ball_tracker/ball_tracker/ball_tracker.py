import typing

import cv2
import numpy as np

from .logger import Logger
from .settings import BallDetectionSettings, ColourDetectionSettings
from .snapshot import SnapShot
from .util import Image, dist_between_two_balls, get_mask_contours_for_colour

Keypoints = typing.Dict[str, typing.List[cv2.KeyPoint]]


class BallTracker():
    def __init__(self, logger: Logger=None, colour_settings: ColourDetectionSettings=None, 
                 ball_settings: BallDetectionSettings=None, **kwargs):
        """Creates an instance of BallTracker that detects balls in images provided to it
        and maps colours to each ball detected.

        :param logger: logger that contains snapshots to log to, defaults to None
        :type logger: Logger, optional
        :param colour_settings: colour detection settings instance, defaults to None
        :type colour_settings: ColourDetectionSettings, optional
        :param ball_settings: ball detection settings instance, defaults to None
        :type ball_settings: BallDetectionSettings, optional
        :param **kwargs: dictionary of options to use to configure
                         the underlying blob detector to detect balls with
        """
        self.logger = logger or Logger()
        
        self.__last_shot_snapshot = self.logger.last_shot_snapshot
        self.__cur_shot_snapshot = self.logger.cur_shot_snapshot
        self.__temp_snapshot = self.logger.temp_snapshot
        self.__white_status_setter = self.logger.set_white_status

        self.colour_settings = colour_settings or ColourDetectionSettings()

        self.ball_settings = ball_settings or BallDetectionSettings()
        self.ball_settings.settingsChanged.connect(self.setup_blob_detector)
            
        self.__keypoints: Keypoints = {}
        self.__blob_detector: cv2.SimpleBlobDetector = None
        self.__image_counter = 0
        self.__shot_in_progess = False
        self.setup_blob_detector(**kwargs)

    def setup_blob_detector(self, **kwargs):
        """Setup underlying blob detector with provided kwargs"""
        params = cv2.SimpleBlobDetector_Params()
        params.filterByConvexity = kwargs.get('FILTER_BY_CONVEXITY', self.ball_settings.settings["FILTER_BY_CONVEXITY"])
        params.minConvexity = kwargs.get('MIN_CONVEXITY', self.ball_settings.settings["MIN_CONVEXITY"])
        params.maxConvexity = kwargs.get('MAX_CONVEXITY', self.ball_settings.settings["MAX_CONVEXITY"])
        params.filterByCircularity = kwargs.get('FILTER_BY_CIRCULARITY', self.ball_settings.settings["FILTER_BY_CIRCULARITY"])
        params.minCircularity = kwargs.get('MIN_CIRCULARITY', self.ball_settings.settings["MIN_CIRCULARITY"])
        params.maxCircularity = kwargs.get('MAX_CIRCULARITY', self.ball_settings.settings["MAX_CIRCULARITY"])
        params.filterByInertia = kwargs.get('FILTER_BY_INERTIA', self.ball_settings.settings["FILTER_BY_INERTIA"])
        params.minInertiaRatio = kwargs.get('MIN_INERTIA', self.ball_settings.settings["MIN_INERTIA"])
        params.maxInertiaRatio = kwargs.get('MAX_INERTIA', self.ball_settings.settings["MAX_INERTIA"])
        params.filterByArea = kwargs.get('FILTER_BY_AREA', self.ball_settings.settings["FILTER_BY_AREA"])
        params.minArea = kwargs.get('MIN_AREA', self.ball_settings.settings["MIN_AREA"])
        params.maxArea = kwargs.get('MAX_AREA', self.ball_settings.settings["MAX_AREA"])
        params.filterByColor = kwargs.get('FILTER_BY_COLOUR', self.ball_settings.settings["FILTER_BY_COLOUR"])
        params.blobColor = kwargs.get('BLOB_COLOR', self.ball_settings.settings["BLOB_COLOUR"])
        params.minDistBetweenBlobs = kwargs.get('MIN_DEST_BETWEEN_BLOBS', self.ball_settings.settings["MIN_DIST_BETWEEN_BLOBS"])
        self.__blob_detector = cv2.SimpleBlobDetector_create(params)

    def get_snapshot_report(self) -> str:
        """Creates a report of  snapshots to show the difference between them

        :return: table comparision between `last_shot_snapshot` 
                 and `cur_shot_snapshot` in a string format
        :rtype: str
        """
        report = '--------------------------------------\n'
        report += 'PREVIOUS SNAPSHOT | CURRENT SNAPSHOT \n'
        report += '------------------|-------------------\n'
        for colour in self.__last_shot_snapshot.colours:
            prev_ball_status = f'{colour.lower()}s: {self.__last_shot_snapshot.colours[colour].count}'
            while len(prev_ball_status) < 17:
                prev_ball_status += ' '
            cur_ball_status = f'{colour.lower()}s: {self.__cur_shot_snapshot.colours[colour].count}'
            report += prev_ball_status + ' | ' + cur_ball_status + '\n'
        report += '--------------------------------------\n'
        return report

    def draw_balls(self, frame: np.ndarray, balls: Keypoints):
        """Draws each ball from `balls` onto `frame`

        :param frame: frame to process
        :type frame: np.ndarray
        :param balls: list of balls to draw onto `frame`
        :type balls: Keypoints
        """
        for ball_colour, ball_list in balls.items():
            for ball in ball_list:
                cv2.putText(
                    frame, ball_colour, (int(
                        ball.pt[0] + 10), int(ball.pt[1])),
                    0, 0.6, (0, 255, 0), thickness=2
                )
                cv2.circle(frame, (int(ball.pt[0]), int(ball.pt[1])),
                           int(ball.size / 2), (0, 255, 0))

    def update_balls(self, balls: Keypoints, cur_balls: Keypoints) -> Keypoints:
        """Updates `balls` with previously detected `cur_balls`
        If a ball from `cur_balls` is close enough to a ball in `balls`,
        it is deemed to be the same ball and the ball in `balls` is updated
        with the ball colour info from `cur_balls`

        :param balls: list of detected balls
        :param cur_ball: list of current balls that are were already detected

        :param balls: list of newly detected balls
        :type balls: Keypoints
        :param cur_balls: list of balls that are were detected previously
        :type cur_balls: Keypoints
        :return: list of newly detected balls mapped to their appropriate colours
        :rtype: Keypoints
        """
        for cur_ball in cur_balls:
            matched = False
            for ball_colour in balls:
                if not matched:
                    for i, ball in enumerate(balls[ball_colour]):
                        dist = dist_between_two_balls(cur_ball, ball)
                        if dist <= 0.3:
                            balls[ball_colour][i] = cur_ball
                            matched = True
                            break
                else:
                    break
        return balls

    def process_image(self, image: Image, show_threshold: bool=False, 
                      detect_colour: str=None, mask_colour: bool=False) -> tuple:
        """Process `image` to detect/track balls, determine if a shot has started/finished
        and determine if a ball was potted

        We store 3 different Snapshots:
        - Previous shot SnapShot
        - Current shot SnapShot
        - Temporary shot SnapShot
                
        The `Last shot SnapShot` stores info about the state of the table
        of the last shot taken
                
        The `Current shot SnapShot` stores info about the state of the table
        currently in play before the shot is taken
                
        The `Temporary SnapShot` is used to determine when a shot has
        started and finished, which is determined by comparing the
        Temporary SnapShot with the Current SnapShot

        :param image: image to process, contains 3 frames (RGB, HSV and binary versions of image)
        :type image: Image
        :param show_threshold: if True return a binary version of `image`, defaults to False
        :type show_threshold: bool, optional
        :return: processed image, ball potted if any were and the number of balls potted
        :rtype: tuple
        """
        ball_potted = None
        pot_count = 0

        # Unpack image tuple
        output_frame, binary_frame, hsv_frame = image

        # Every 5 images run the colour detection phase, otherwise just update ball positions
        if self.__image_counter == 0 or self.__image_counter % 5 == 0:
            self.__keypoints = self.perform_colour_detection(binary_frame, hsv_frame)
        else:
            cur_keypoints = self.__blob_detector.detect(binary_frame)
            self.update_balls(self.__keypoints, cur_keypoints)

        if self.__image_counter == 0:
            self.__cur_shot_snapshot.assign_balls_from_dict(self.__keypoints)
            self.__last_shot_snapshot.assign_balls_from_dict(self.__keypoints)

        # Swap output frame with binary frame if show threshold is True
        if show_threshold:
            output_frame = binary_frame

        # Draw contours around a colour to detect if not None
        if detect_colour:
            colour_mask, contours = self.detect_colour(
                hsv_frame, self.colour_settings.colours[detect_colour]["LOWER"], 
                self.colour_settings.colours[detect_colour]["UPPER"])

            # Show only the detected colour in the output frame
            if mask_colour:
                output_frame = cv2.bitwise_and(
                    output_frame, output_frame, mask=colour_mask)

            cv2.drawContours(output_frame, contours, -1, (0, 255, 0), 2)

        # Draw only the balls for the detected colour 
        # if we are only showing the detected colour
        if detect_colour and detect_colour in self.colour_settings.settings["BALL_COLOURS"] and mask_colour:
            self.draw_balls(output_frame, { detect_colour: self.__keypoints[detect_colour] })
        else:
            # Otherwise just draw all detected balls
            self.draw_balls(output_frame, self.__keypoints)

        # Every 5 images run the snapshot comparision/generation phase
        if self.__image_counter == 0 or self.__image_counter % 5 == 0:
            ball_status = None

            self.__temp_snapshot.assign_balls_from_dict(self.__keypoints)

            if not self.__shot_in_progess:
                self.__shot_in_progess = self.has_shot_started(self.__temp_snapshot, self.__cur_shot_snapshot)

            if self.__shot_in_progess:
                if self.has_shot_finished(self.__temp_snapshot, self.__cur_shot_snapshot):
                    for ball_colour in self.__last_shot_snapshot.colours:
                        count = self.__last_shot_snapshot.compare_ball_diff(
                            ball_colour, self.__temp_snapshot
                        )
                        if ball_colour != 'WHITE' and count > 0:
                            ball_potted = ball_colour
                            pot_count = count
                            ball_status = 'Potted {} {}/s'.format(
                                pot_count, ball_potted.lower())

                    if ball_status is not None:
                        print(ball_status)
                    print('===========================================\n')
                    self.__last_shot_snapshot.assign_balls_from_snapshot(self.__cur_shot_snapshot)
                    self.__shot_in_progess = False
        
                if self.__cur_shot_snapshot.white and self.__temp_snapshot.white:
                    self.__cur_shot_snapshot.white.is_moving = self.__temp_snapshot.white.is_moving
            self.__cur_shot_snapshot.assign_balls_from_snapshot(self.__temp_snapshot)

        self.__image_counter += 1

        return output_frame, ball_potted, pot_count

    def perform_colour_detection(self, binary_frame: np.ndarray, hsv_frame: np.ndarray) -> Keypoints:
        """Performs the colour detection process

        This method handles the colour detection phase and returns a list of
        detected balls in the image and maps the appropriate colour to each ball

        :param binary_frame: binary frame where detected balls are white on a black background
        :type binary_frame: np.ndarray
        :param hsv_frame: HSV frame to detect colours with
        :type hsv_frame: np.ndarray
        :return: list of keypoints mapped to an appropriate colour found in `binary_frame`
        :rtype: Keypoints
        """

        balls: Keypoints = { 
            colour: list() for colour in self.colour_settings.settings["BALL_COLOURS"] 
        }

        colour_contours: typing.List[np.ndarray] = {
            colour: list() for colour in self.colour_settings.settings["BALL_COLOURS"] 
        }

        # Detect balls in the binary image (White circles on a black background)
        keypoints = self.__blob_detector.detect(binary_frame)

        # Obtain colours contours for each ball colour from the HSV colour space of the image
        for colour, properties in self.colour_settings.settings["BALL_COLOURS"].items():
            if properties["DETECT"]:
                _, contours = get_mask_contours_for_colour(hsv_frame, colour, self.colour_settings.colours)
                colour_contours[colour] = contours

        # Get colours in their detection order
        colours = sorted(self.colour_settings.settings["BALL_COLOURS"], 
            key=lambda colour: self.colour_settings.settings["BALL_COLOURS"][colour]["ORDER"])

        # For each ball found, determine what colour it is and add it to the list of balls
        # If a ball is not mapped to an appropriate colour, it is discarded
        for keypoint in keypoints:
            for colour in colours:
                if self.colour_settings.settings["BALL_COLOURS"][colour]["DETECT"]:
                    if self.__keypoint_is_ball(colour, 
                            colour_contours[colour], keypoint, balls):
                        break

        return balls

    def __keypoint_is_ball(self, colour: str, colour_contours: typing.List[np.ndarray], 
                           keypoint: cv2.KeyPoint, balls: Keypoints, 
                           biggest_contour: bool=False) -> bool:
        """Determine if `keypoint` is a ball of `colour`

        :param colour: colour to check `keypoint` against
        :type colour: str
        :param colour_contours: contours of `colour`
        :type colour_contours: typing.List[np.ndarray]
        :param keypoint: keypoint to check
        :type keypoint: cv2.KeyPoint
        :param balls: list of balls already detected
        :type balls: Keypoints
        :param biggest_contour: use only the biggest contour in `colour_contours` 
                                to determine if `keypoint` is a ball of `colour`, defaults to False
        :type biggest_contour: bool, optional
        :return: True if `keypoint` is within `contour`, False otherwise
        :rtype: bool
        """
        if len(colour_contours) > 1 and biggest_contour:
            colour_contour = max(
                colour_contours, key=lambda el: cv2.contourArea(el))
            if self.__keypoint_in_contour(keypoint, colour_contour):
                balls[colour].append(keypoint)
                return True
        else:
            for contour in colour_contours:
                if self.__keypoint_in_contour(keypoint, contour):
                    balls[colour].append(keypoint)
                    return True
        return False

    def __keypoint_in_contour(self, keypoint: cv2.KeyPoint, contour: np.ndarray) -> bool:
        """Determine if `keypoint` is contained within `contour`

        :param keypoint: keypoint to check
        :type keypoint: cv2.KeyPoint
        :param contour: contour to check
        :type contour: np.ndarray
        :return: True if `keypoint` is within `contour`, False otherwise
        :rtype: bool
        """
        dist = cv2.pointPolygonTest(contour, keypoint.pt, False)
        return True if dist == 1 else False

    def detect_colour(self, frame: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> tuple:
        """Detects a colour in `frame` based on the `lower` and `upper` HSV values

        :param frame: frame to process
        :type frame: np.ndarray
        :param lower: lower range of colour HSV values
        :type lower: np.ndarray
        :param upper: upper range of colour HSV values
        :type upper: np.ndarray
        :return: colour mask of `lower` and `upper` HSV values and a list of contours
        :rtype: tuple
        """
        colour_mask = cv2.inRange(frame, lower, upper)
        contours, _ = cv2.findContours(
            colour_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        return colour_mask, contours

    def has_shot_started(self, first_snapshot: SnapShot, second_snapshot: SnapShot) -> bool:
        """Determine if the shot has started by comparing `first_snapshot` white ball
        with `second_snapshot` white ball

        :param first_snapshot: first snapshot
        :type first_snapshot: SnapShot
        :param second_snapshot: second snapshot
        :type second_snapshot: SnapShot
        :return: True if the shot has started, otherwise False
        :rtype: bool
        """
        if first_snapshot.colours["WHITE"].count > 0:
            if first_snapshot.colours["WHITE"].count == second_snapshot.colours["WHITE"].count:
                if first_snapshot.white and second_snapshot.white:
                    if self.has_ball_moved(first_snapshot.white.keypoint, second_snapshot.white.keypoint):
                        print('===========================================')
                        print('WHITE STATUS: moving...')
                        self.__white_status_setter(True)
                        return True
                return False
        return False

    def has_shot_finished(self, first_snapshot: SnapShot, second_snapshot: SnapShot) -> bool:
        """Determine if the shot has finished by comparing `first_snapshot` white ball
        with `second_snapshot` white ball

        :param first_snapshot: first snapshot
        :type first_snapshot: SnapShot
        :param second_snapshot: second snapshot
        :type second_snapshot: SnapShot
        :return: True if the shot has finished, otherwise False
        :rtype: bool
        """
        if first_snapshot.colours["WHITE"].count > 0:
            if first_snapshot.colours["WHITE"].count == second_snapshot.colours["WHITE"].count:
                if first_snapshot.white and second_snapshot.white:
                    if self.has_ball_stopped(first_snapshot.white.keypoint, second_snapshot.white.keypoint):
                        print('WHITE STATUS: stopped...\n')
                        self.__white_status_setter(False)
                        return True
                else:
                    return True
        return False

    def has_ball_stopped(self, first_ball: cv2.KeyPoint, second_ball: cv2.KeyPoint) -> bool:
        """Determine if a specific ball has stopped

        :param first_ball: first ball
        :type first_ball: cv2.KeyPoint
        :param second_ball: second ball
        :type second_ball: cv2.KeyPoint
        :return: True if the ball has stopped, otherwise False
        :rtype: bool
        """
        dist = dist_between_two_balls(first_ball, second_ball)
        return True if dist <= 0.1 else False

    def has_ball_moved(self, first_ball: cv2.KeyPoint, second_ball: cv2.KeyPoint) -> bool:
        """Determine if a specific ball has moved

        :param first_ball: first ball
        :type first_ball: cv2.KeyPoint
        :param second_ball: second ball
        :type second_ball: cv2.KeyPoint
        :return: True if the ball has moved, otherwise False
        :rtype: bool
        """
        dist = dist_between_two_balls(first_ball, second_ball)
        return True if dist > 0.1 else False