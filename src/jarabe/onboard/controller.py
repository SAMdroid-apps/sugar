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
        self._bound_steps = []
        self._completed_steps = []
        self._hotspots = {}
        self._view = None

        self._settings = Gio.Settings(schema='org.sugarlabs.onboard')
        self._settings.connect('changed', self.__settings_change_cb)
        self.__settings_change_cb(self._settings, None)

    def __settings_change_cb(self, settings, keys):
        new_steps = map(int, self._settings.get_strv('current-steps'))
        if len(new_steps) == 0:
            new_steps = INITIAL_STEPS

        if self._steps != new_steps:
            for step_id in new_steps:
                if step_id not in self._steps:
                    self.show_step_hotspot(STEPS[step_id])
            self._steps = new_steps

        self._completed_steps = map(int,
                                    self._settings.get_strv('completed-steps'))
        # Hide hotspots for completed steps
        for index, hotspot in self._hotspots.iteritems():
            if index in self._completed_steps:
                hotspot.hide()
                hotspot.destroy()
                del self._hotspots[index]
        # Unbind completed steps
        new_bound_steps = self._bound_steps
        for index in self._bound_steps:
            if index in self._completed_steps:
                STEPS[index].unbind_done_listeners()
                new_bound_steps.remove(index)
        self._bound_steps = new_bound_steps

        # Bind all uncompleted and unbound steps
        for index, step in enumerate(STEPS):
            if step not in self._completed_steps and \
               step not in self._bound_steps and \
               step.props.process == self.process:
                step.done_signal.connect(self.__step_done_cb)
                step.bind_done_listeners()
                self._bound_steps.append(index)

    def show_step_hotspot(self, step):
        if step.props.process != self.props.process:
            return
        if STEPS.index(step) in self._completed_steps:
            return

        selector, scale = step.get_hotspot_location()
        if selector is None:
            self._display_step_view(step)
        elif scale == HotspotScale.KEYPRESS:
            hotspot = KeyPressHotspot(selector)
            hotspot.show()
            self._hotspots[STEPS.index(step)] = hotspot
        else:
            get_widget_registry().wait_for(
                selector, self.__got_widget_cb, (step, scale))

    def __got_widget_cb(self, widget, user_data):
        step, scale = user_data
        hotspot = Hotspot(widget, scale)
        hotspot.activate_signal.connect(self.__hotspot_activate_cb, step)
        self._hotspots[STEPS.index(step)] = hotspot

    def __hotspot_activate_cb(self, hotspot, step):
        hotspot.disconnect_by_func(self.__hotspot_activate_cb)
        del self._hotspots[STEPS.index(step)]
        self._display_step_view(step)

    def _display_step_view(self, step):
        view = StepView(step)
        self._set_view(view)

    def __step_done_cb(self, step):
        print('STEP DONE', step)
        step.disconnect_by_func(self.__step_done_cb)
        step.unbind_done_listeners()

        if self._view is not None and self._view.props.step == step:
            self._view.done()
        if STEPS.index(step) in self._hotspots:
            hotspot = self._hotspots[STEPS.index(step)]
            hotspot.destroy()

        if STEPS.index(step) in self._steps:
            self._steps.remove(STEPS.index(step))
        self._completed_steps.append(STEPS.index(step))

        for id in step.props.children:
            if id not in self._completed_steps and \
               id not in self._steps:
                self._steps.append(id)
                step = STEPS[id]
                self.show_step_hotspot(step)

        self._settings.handler_block_by_func(self.__settings_change_cb)
        try:
            self._settings.set_strv('current-steps', map(str, self._steps))
            self._settings.set_strv('completed-steps',
                                    map(str, self._completed_steps))
        finally:
            self._settings.handler_unblock_by_func(self.__settings_change_cb)

    def _set_view(self, view):
        if self._view is not None:
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


_controller = None
def get_onboarding_controller():
    global _controller
    if _controller is None:
        _controller = OnboardingController()
    return _controller

def start_onboarding_controller():
    get_onboarding_controller()
