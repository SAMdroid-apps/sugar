from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

from sugar3.graphics import style
from sugar3.graphics.icon import Icon
from sugar3.graphics.animator import Animator, Animation


class Quadrent(object):
    TOP_LEFT = 0
    TOP_RIGHT = 1
    BOTTOM_LEFT = 2
    BOTTOM_RIGHT = 3

    @staticmethod
    def next(quadrent):
        return (quadrent + 1) % 4


_MAX_WIDTH = style.GRID_CELL_SIZE * 3


class StepView(Gtk.Window):
    def __init__(self, step):
        Gtk.Window.__init__(self)
        self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        self._step = step
        self._animator = None

        self.props.type_hint = Gdk.WindowTypeHint.DOCK
        self.set_decorated(False)
        self.props.gravity = Gdk.Gravity.CENTER
        self.move(*self._quadrent_center(Quadrent.TOP_LEFT))

        self.set_default_size(_MAX_WIDTH, _MAX_WIDTH)
        self.props.hexpand = False
        self.props.vexpand = True

        context = self.get_style_context()
        # Just assume all borders are the same
        border = context.get_border(Gtk.StateFlags.ACTIVE).right
        self.set_border_width(border)

        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self._box)
        self._box.show()

        self._top_label = self._make_label(
            '<big><b>{}</b></big>\n{}'.format(
            self._step.props.title,
            self._step.props.body))
        self._box.add(self._top_label)
        self._top_label.show()

        if self._step.props.image is not None:
            self._image = Icon(
                icon_name=self._step.props.image,
                pixel_size=_MAX_WIDTH)
            self._box.add(self._image)
            self._image.show()

        self._bottom_label = self._make_label(
            '<i>{}</i>'.format(
            self._step.props.continue_string))
        self._box.add(self._bottom_label)
        self._bottom_label.show()

    def _make_label(self, markup):
        l = Gtk.Label()
        l.set_markup(markup)
        l.set_line_wrap(True)
        l.props.hexpand = False
        l.props.vexpand = True
        l.props.width_request = _MAX_WIDTH
        return l

    def _get_quadrent(self, x, y):
        width = Gdk.Screen.width()
        height = Gdk.Screen.height()
        mid_x = width/2
        mid_y = height/2
        if x > mid_x:
            if y > mid_y:
                return Quadrent.BOTTOM_RIGHT
            else:
                return Quadrent.TOP_RIGHT
        else:
            if y > mid_y:
                return Quadrent.BOTTOM_LEFT
            else:
                return Quadrent.TOP_LEFT

    def _quadrent_center(self, quad):
        width = Gdk.Screen.width()
        height = Gdk.Screen.height()
        mid_x = width/2
        mid_y = height/2
        qx = width/4
        qy = height/4
        if quad == Quadrent.TOP_LEFT:
            return (qx, qy)
        elif quad == Quadrent.TOP_RIGHT:
            return (mid_x + qx, qy)
        elif quad == Quadrent.BOTTOM_LEFT:
            return (qx, mid_y + qy)
        elif quad == Quadrent.BOTTOM_RIGHT:
            return (mid_x + qx, mid_y + qy)

    def do_event(self, event):
        if event.type == Gdk.EventType.ENTER_NOTIFY:
            curr = self._get_quadrent(*self.get_position())
            new = Quadrent.next(curr)
            destx, desty = self._quadrent_center(new)
            alloc = self.get_allocation()

            # The width is constant, and will be never be an issue
            # if the screen is more than 6 grid cells wide (assert true).
            if desty + alloc.height > Gdk.Screen.height():
                desty -= desty + alloc.height - Gdk.Screen.height()
            dest = (destx, desty)
            
            if self._animator is not None:
                self._animator.stop()
            self._animator = Animator(1)
            self._animator.add(_MoveAnimation(self, self.get_position(), dest))
            self._animator.start()

    @GObject.property
    def step(self):
        return self._step

if hasattr(StepView, 'set_css_name'):
    StepView.set_css_name('palette')


class _MoveAnimation(Animation):
    def __init__(self, window, source, dest):
        Animation.__init__(self, 0.0, 1.0)
        self._window = window
        self._source = source
        self._dest = dest

    def next_frame(self, frame):
        inv = 1.0 - frame
        x = (frame * self._dest[0]) + (inv * self._source[0])
        y = (frame * self._dest[1]) + (inv * self._source[1])
        self._window.move(int(x), int(y))
