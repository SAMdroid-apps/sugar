import logging
import os

from gi.repository import GObject
from gi.repository import Gio

from jarabe.onboard.steps import STEPS, INITIAL_STEPS, Processes
from jarabe.onboard.view import StepView
from jarabe.onboard.hotspot import (Hotspot, get_widget_registry, HotspotScale,
                                    KeyPressHotspot)


class OnboardingController(GObject.GObject):
    '''
    A manager for the onboarding system, built to be used across
    multiple processes.
    '''

    process = GObject.Property(type=int)

    def __init__(self):
        GObject.GObject.__init__(self)
        if 'SUGAR_ACTIVITY_ROOT' in os.environ:
            self.process = Processes.ACTIVITY
        else:
            self.process = Processes.SHELL
        self._steps = []
        self._view = None
        self._settings = Gio.Settings(schema='org.sugarlabs.onboard')
        self._settings.connect('changed', self.__settings_change_cb)
        self.__settings_change_cb(self._settings, None)

    def __settings_change_cb(self, settings, keys):
        new_steps = map(int, self._settings.get_strv('current-steps'))
        if len(new_steps) == 0:
            new_steps = INITIAL_STEPS
        if self._settings.get_boolean('completed'):
            new_steps = []

        if self._steps != new_steps:
            for step_id in new_steps:
                if step_id not in self._steps and step_id < len(STEPS):
                    self.show_step_hotspot(STEPS[step_id])
            self._steps = new_steps

    def show_step_hotspot(self, step):
        if step.props.process != self.props.process:
            return

        selector, scale = step.get_hotspot_location()
        if selector is None:
            self._display_step_view(step)
        elif scale == HotspotScale.KEYPRESS:
            hotspot = KeyPressHotspot(selector)
            hotspot.show()
            step.done_signal.connect(self.__key_step_done_cb, hotspot)
            step.bind_done_listeners()
        else:
            get_widget_registry().wait_for(
                selector, self.__got_widget_cb, (step, scale))

    def __got_widget_cb(self, widget, user_data):
        step, scale = user_data
        hotspot = Hotspot(widget, scale)
        hotspot.activate_signal.connect(self.__hotspot_activate_cb, step)

    def __hotspot_activate_cb(self, hotspot, step):
        hotspot.disconnect_by_func(self.__hotspot_activate_cb)
        self._display_step_view(step)

    def _display_step_view(self, step):
        view = StepView(step)
        self._set_view(view)

        step.done_signal.connect(self.__step_done_cb, view)
        step.bind_done_listeners()

    def __step_done_cb(self, step, view):
        step.disconnect_by_func(self.__step_done_cb)
        view.done()
        self._done_step(step)

    def __key_step_done_cb(self, step, hotspot):
        step.disconnect_by_func(self.__key_step_done_cb)
        view = StepView(step)
        self._set_view(view)

        hotspot.hide()
        hotspot.destroy()
        self._done_step(step)

    def _set_view(self, view):
        if self._view is not None:
            if hasattr(self._view.props, 'step'):
                step = self._view.props.step
                index = STEPS.index(step)
                if index in self._steps and \
                   not view.props.step == self._view.props.step:
                    # Unfinished, so shot the hotspot again
                    self.show_step_hotspot(step)
            self._view.hide()
            self._view.destroy()
        self._view = view
        self._view.show()

    def _done_step(self, step):
        if STEPS.index(step) in self._steps:
            self._steps.remove(STEPS.index(step))
        else:
            logging.error('Removing step that is not active %r', step)

        for id in step.props.children:
            self._steps.append(id)
            if id < len(STEPS):
                step = STEPS[id]
                self.show_step_hotspot(step)
        if self._steps == []:
            self._settings.set_boolean('completed', True)

        self._settings.set_strv('current-steps', map(str, self._steps))

_controller = None
def get_onboarding_controller():
    global _controller
    if _controller is None:
        _controller = OnboardingController()
    return _controller

def start_onboarding_controller():
    get_onboarding_controller()
