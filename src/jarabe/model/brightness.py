# Copyright (C) 2014 Sam Parkinson
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os

from sugar3 import dispatch


_DISPLAYS_DIRECTORY = '/sys/class/backlight/'


class Brightness(object):

    brightness_changed = dispatch.Signal()

    def __init__(self):

        display = os.listdir(_DISPLAYS_DIRECTORY)[0]
        brightness_directory = os.path.join(_DISPLAYS_DIRECTORY, display)
        self._brightness_path = os.path.join(brightness_directory,
                                             'brightness')
        self._can_set_beightness = os.access(self._brightness_path, os.W_OK)

        with open(os.path.join(brightness_directory, 'max_brightness')) as f:
            self._max_brightness = int(f.read())

    def get_brightness(self):
        with open(self._brightness_path) as f:
            return int(f.read())

    def set_brightness(self, brightness):
        '''
        Sets the brightness with an int ranging from 0 to max_brightness.
        '''
        if brightness < 0 or brightness > self._max_brightness:
            return

        if self._can_set_beightness:
            with open(self._brightness_path, 'w') as f:
                f.write(str(brightness))

        self.brightness_changed.send(None)

    def can_set_brightness(self):
        return self._can_set_beightness

    def get_max_brightness(self):
        return self._max_brightness

    def get_brightness_levels(self):
        return self._max_brightness + 1


brightness = Brightness()
