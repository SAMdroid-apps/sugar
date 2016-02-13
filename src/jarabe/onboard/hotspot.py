import math
import logging

import cairo
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject

from sugar3.graphics import style
from sugar3.graphics.icon import Icon
from sugar3.graphics.animator import Animator, Animation


class WidgetRegistry(GObject.GObject):
    def __init__(self):
        GObject.GObject.__init__(self)
        self._widgets = {}
        self._waits = {}

    def register(self, selector, widget):
        self._widgets[selector] = widget
        widget.connect('destroy', self.__widget_destroy_cb, selector)

        if '#' in selector:
            # Add a selector:latest copy (in addition to selector#id)
            new_selector = selector[:selector.index('#')] + ':latest'
            self.register(new_selector, widget)

        if selector in self._waits:
            for cb, user_data in self._waits[selector]:
                cb(widget, user_data)
            del self._waits[selector]

    def __widget_destroy_cb(self, widget, selector):
        if self._widgets.get(selector) is widget:
            del self._widgets[selector]

    def get(self, selector):
        return self._widgets.get(selector)

    def get_all(self, selector_fragment):
        for k, v in self._widgets.iteritems():
            if selector_fragment in k:
                yield v

    def wait_for(self, selector, callback, user_data):
        if self.get(selector) is not None:
            callback(self.get(selector), user_data)
            return
        if not selector in self._waits:
            self._waits[selector] = []
        self._waits[selector].append((callback, user_data))
        


_widget_registry = None
def get_widget_registry():
    global _widget_registry
    if _widget_registry is None:
        _widget_registry = WidgetRegistry()
    return _widget_registry


class HotspotScale(object):
    NORMAL = 1.0
    # The help icon is a circle around the size of NORMAL, so it is hard to see
    HELP_ICON = 1.2
    LARGE = 2.0
    KEYPRESS = -1


class KeyPressHotspot(Gtk.Window):
    def __init__(self, key):
        Gtk.Window.__init__(self)
        self.set_decorated(False)
        self.set_default_size(style.STANDARD_ICON_SIZE,
                              style.STANDARD_ICON_SIZE)
        self.move(0, 0)
        self.override_background_color(
            Gtk.StateFlags.NORMAL,
            Gdk.RGBA(*style.COLOR_TOOLBAR_GREY.get_rgba()))
        self.props.type_hint = Gdk.WindowTypeHint.DOCK

        self._up_icon = Icon(icon_name='key-{}-up'.format(key),
                             pixel_size=style.STANDARD_ICON_SIZE)
        self._down_icon = Icon(icon_name='key-{}-down'.format(key),
                               pixel_size=style.STANDARD_ICON_SIZE)
        self.add(self._down_icon)
        GLib.timeout_add(1000, self.__switch_icon_cb, False)

    def __switch_icon_cb(self, up):
        if self.get_child() is not None:
            self.get_child().hide()
            self.remove(self.get_child())

        if up:
            self.add(self._up_icon)
        else:
            self.add(self._down_icon)
        self.get_child().show()

        GLib.timeout_add(1000, self.__switch_icon_cb, not up)

# TODO: Sugar-scaling, this is all at 100x
_CENTER = 35
_TOLERENCE = 20
_CIRCLES = [(35, 0.1), (28, 0.2), (21, 0.3), (14, 0.4), (7, 0.5)]
_WIN_SIZE = 35 * 2
_INTERVAL = 80


class Hotspot(GObject.GObject):
    '''
    This is a hotspot that pulses and is displayed over the top of
    a widget.  It can be activated it the user moves their mouse
    towards the center of the widget.

    Args:
        widget (Gtk.Widget):  the hotspot will be centered
            around this widget, and draw in the context of
            it's toplevel (eg. Gtk.Window)

    Kwargs:
        scale (float):  A scale for the widget, see :class:`HotspotScale`

    Implementation
    ==============

    The hotspot is drawn as a collection of circles.  Importantly, it
    is drawn as part of the widget's toplevel (eg. Gtk.Window) rather
    than as part of the window itself.  This allows the hotspot to
    overflow the widget's clip.

    It also processes mouse move events from the toplevel rather than
    the widget.  This is important, as a) the trigger are may extend
    outside the widget sometimes and b) some Gtk.Widget's can not
    receive pointer events (eg. Toolbuttons) whereas the toplevel
    always can.
    '''

    activate_signal = GObject.Signal('activate')

    def __init__(self, widget, scale=1.0):
        GObject.GObject.__init__(self)
        self._widget = widget
        self._widget.connect('hierarchy-changed', self.__hierachy_changed_cb)
        self._widget.connect('hide', self.__visibility_changed_cb)
        self._widget.connect('show', self.__visibility_changed_cb)

        self._state = 1.0
        self._x = 0
        self._y = 0
        self._scale = scale
        self._subdraw = False
        self._animator = Animator(1)
        self._animator.add(_StateAnimation(self))
        self._pulse_sid = None
        self._pulse_direction = +1

        tl = self._widget.get_toplevel()
        if tl is not None:
            self.__hierachy_changed_cb(self._widget)

    def __hierachy_changed_cb(self, widget, previous_toplevel=None):
        alloc = self._widget.get_allocation()
        if alloc.x == -1 or alloc.y == -1:
            GLib.timeout_add(500, self.__try_hc_again_cb, widget)
            return
            
        r = self._widget.translate_coordinates(
            self._widget.get_toplevel(),
            (alloc.width/2), (alloc.height/2))
        if r is None:
            GLib.timeout_add(500, self.__try_hc_again_cb, widget)
            return
        else:
            self._x, self._y = r

        tl = self._widget.get_toplevel()
        tl.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        tl.connect('event', self.__event_cb)
        tl.connect('draw', self.__draw_cb)
        self._redraw()

        if self._pulse_sid is None:
            self._pulse_sid = GLib.timeout_add(_INTERVAL, self.__pulse_cb)

    def __try_hc_again_cb(self, widget):
        self.__hierachy_changed_cb(self, widget)
        return False  # Do not call again

    def __pulse_cb(self):
        self._state += self._pulse_direction * 0.02
        if self._state >= 1.2:
            self._pulse_direction = -1
        elif self._state <= 1.0:
            self._pulse_direction = +1
        self._redraw()
        return True

    def _redraw(self):
        tl = self._widget.get_toplevel()
        # Be safe and make sure to invalidate a little too much
        # so that we don't leave any artifacts onscreen
        r = _CENTER * self._scale * (self._state + 0.02) + 1
        tl.queue_draw_area(
            int(self._x - r), int(self._y - r),
            int(r*2), int(r*2))

    def __visibility_changed_cb(self, widget):
        tl = self._widget.get_toplevel()
        if tl is not None:
            self._redraw()

    def __draw_cb(self, widget, event):
        if self._subdraw or not (self._widget.is_visible() \
           and self._widget.get_mapped()):
            return
        # Sadly it is recursive if we are not careful
        self._subdraw = True
        widget.draw(event)
        self._subdraw = False

        cr = Gdk.cairo_create(widget.get_window())
        for r, a in _CIRCLES:
            cr.arc(self._x, self._y, r*self._scale*self._state, 0, 2 * math.pi)
            cr.set_source_rgba(0.8, 0.8, 0.8, a*max(0.5, self._state))
            cr.fill()
        return True

    def __event_cb(self, widget, event):
        if not (self._widget.is_visible() and self._widget.get_mapped()):
            return False

        if event.type == Gdk.EventType.MOTION_NOTIFY:
            # List views, etc. cause issues where the .x and .y attrs
            # are relative to the list view rather than the toplevel
            tlx, tly = self._widget.get_toplevel().get_position()
            x = event.x_root - tlx
            y = event.y_root - tly

            if self._state < 1.0:  # Drift to cursor if animating out
                self._x = x
                self._y = y
            elif abs(x - self._x) < _TOLERENCE*self._scale \
               and abs(y - self._y) < _TOLERENCE*self._scale:
                self._animator.start()
                self.activate_signal.emit()
                if self._pulse_sid is not None:
                    GLib.source_remove(self._pulse_sid)

        return False  # Pass on this event

    def set_state(self, frame):
        if frame == 0.0:
            self.destroy()
        else:
            self._state = frame
            self._redraw()

    def destroy(self):
        self._widget.disconnect_by_func(self.__hierachy_changed_cb)

        tl = self._widget.get_toplevel()
        try:
            tl.disconnect_by_func(self.__draw_cb)
            tl.disconnect_by_func(self.__event_cb)
        except TypeError:
            # The widget was never mapped so we could never bind the toplevel
            pass

        if self._pulse_sid is not None:
            GLib.source_remove(self._pulse_sid)
        del self


class _StateAnimation(Animation):
    def __init__(self, hotspot):
        Animation.__init__(self, 1.0, 0)
        self._hotspot = hotspot

    def next_frame(self, frame):
        self._hotspot.set_state(frame)
