from gettext import gettext as _
from gi.repository import GObject

from jarabe.model import shell
from jarabe.onboard.hotspot import get_widget_registry, HotspotScale


class Processes(object):
    SHELL = 0
    ACTIVITY = 1


class Step(GObject.GObject):
    '''
    Steps are the basic object for the onboarding system.  They
    go through the following lifecycle:

    1. The step is bound (see :func:`bind_done_listeners`)
    2. The done_signal is emitted
    3. The step is marked as done, and :func:`unbind_done_listeners` is
       called

    During that lifecycle, the step can have a hotspot displayed (see
    :func:`get_hotspot_location`) and a informational window can be shows
    (see the title, body and continue_string properties).  This is slightly
    different for a "keypress" step, as the informational window is shown
    after the done_signal regardless of the source of the event.

    Args:
        title (str):  a small string (~4 words) to display in bold at the top
        body (str):  an elaboration on the text string, explain the step
        continue_string (str):  a reiteration of how to complete the
            step, usually in the format "Do X to continue"
        children (list of indexes):  indexes of the children steps of this
            Step in the "STEPS" constant array
        image (str):  the name of an image in the icon path (technically an
            icon name) that is square.  It will be displayed in the
            popup that users see when they hover over the hotspot.

    Kwargs:
        process (Process.*):  the process this Step should run in, either
            in an activity process or in the shell

    The strings are also accessed through GProps, which can be
    overridden if the step needs dynamic text generation.
    '''

    done_signal = GObject.Signal('done')

    def __init__(self, title, body, continue_string, children, image=None,
                 process=Processes.SHELL):
        GObject.GObject.__init__(self)
        self._title = title
        self._body = body
        self._continue_string = continue_string
        self._children = children
        self._process = process
        self._image = image

    @GObject.Property
    def title(self):
        return self._title

    @GObject.Property
    def body(self):
        return self._body

    @GObject.Property
    def continue_string(self):
        return self._continue_string

    @GObject.Property
    def children(self):
        return self._children

    @GObject.Property
    def process(self):
        return self._process

    @GObject.Property
    def image(self):
        return self._image

    def get_hotspot_location(self):
        '''
        Get the location that the hotspot should be located over

        Returns tuple (str, float) widget registry selector, scale of hotspot
            or (None, None) for no hotspot (immediately show step info),
            or (key, HotspotScale.KEYPRESS) for key press hotspot
        '''
        return None

    def bind_done_listeners(self):
        self.done_signal.emit()

    def unbind_done_listeners(self):
        pass


class ActivityIconHoverStep(Step):
    def get_hotspot_location(self):
        return 'activity_icon#org.laptop.AbiWordActivity', HotspotScale.NORMAL

    def bind_done_listeners(self):
        for widget in get_widget_registry().get_all('activity_icon#'):
            invoker = widget.props.palette_invoker
            invoker.connect('popup', self.__popup_cb)

    def unbind_done_listeners(self):
        for widget in get_widget_registry().get_all('activity_icon#'):
            invoker = widget.props.palette_invoker
            invoker.disconnect_by_func(self.__popup_cb)
            if invoker.props.palette is not None:
                try:
                    invoker.props.palette.disconnect_by_func(
                        self.__secondary_popup_cb)
                except TypeError:
                    pass  # Not bound

    def __popup_cb(self, invoker):
        invoker.props.palette.connect(
            'secondary-popup', self.__secondary_popup_cb)

    def __secondary_popup_cb(self, palette):
        self.done_signal.emit()


class LaunchActivityStep(Step):
    def get_hotspot_location(self):
        return None, None

    @GObject.Property
    def body(self):
        name = _('this activity')
        widget = get_widget_registry().get('activity_palette_start_new')
        if widget is not None:
            name = widget.activity_name
        return self._body % {'activity name': name}

    def bind_done_listeners(self):
        model = shell.get_model()
        model.connect('launch-started', self.__launch_started_cb)

    def unbind_done_listeners(self):
        shell.get_model().disconnect_by_func(self.__launch_started_cb)

    def __launch_started_cb(self, model, activity):
        self.done_signal.emit()


class ChangeTitleStep(Step):
    def get_hotspot_location(self):
        # Yes, it is in a toolbar, but it is too close
        # to the frame hot corner - it is just hard if it
        # it toolbar scale
        return 'activity_button', HotspotScale.NORMAL

    def bind_done_listeners(self):
        widget = get_widget_registry().get('title_entry')
        widget.entry.connect('changed', self.__entry_changed_cb)

    def unbind_done_listeners(self):
        widget = get_widget_registry().get('title_entry')
        widget.entry.disconnect_by_func(self.__entry_changed_cb)

    def __entry_changed_cb(self, entry):
        self.done_signal.emit()


class ChangeDescriptionStep(Step):
    def get_hotspot_location(self):
        return 'description_item', HotspotScale.NORMAL

    def bind_done_listeners(self):
        widget = get_widget_registry().get('description_item')
        widget.changed_signal.connect(self.__changed_cb)

    def unbind_done_listeners(self):
        widget = get_widget_registry().get('description_item')
        widget.disconnect_by_func(self.__changed_cb)

    def __changed_cb(self, widget):
        self.done_signal.emit()
        

class OpenFrameStep(Step):
    def get_hotspot_location(self):
        return 'F6', HotspotScale.KEYPRESS

    def bind_done_listeners(self):
        from jarabe import frame
        self._frame = frame.get_view()
        self._frame.show_signal.connect(self.__done_cb)

    def unbind_done_listeners(self):
        self._frame.disconnect_by_func(self.__done_cb)

    def __done_cb(self, frame):
        self.done_signal.emit()
        frame.disconnect_by_func(self.__done_cb)


class DragToClipboardStep(Step):
    def get_hotspot_location(self):
        return 'clipboard_tray', HotspotScale.NORMAL

    def bind_done_listeners(self):
        from jarabe.frame import clipboard
        self._cb_service = clipboard.get_instance()
        self._cb_service.connect('object-added', self.__done_cb)

    def unbind_done_listeners(self):
        self._cb_service.disconnect_by_func(self.__done_cb)

    def __done_cb(self, cb_service, cb_object):
        self.done_signal.emit()


class DragFromClipboardStep(Step):
    _child = None

    def get_hotspot_location(self):
        return 'clipboard_icon', HotspotScale.NORMAL

    def bind_done_listeners(self):
        get_widget_registry().wait_for('clipboard_icon', self.__got_widget_cb,
                                       None)

    def __got_widget_cb(self, widget, user_data):
        self._child = widget.get_child()
        self._child.connect('drag-begin', self.__done_cb)

    def unbind_done_listeners(self):
        if self._child is not None:
            self._child.disconnect_by_func(self.__done_cb)
        self._child = None

    def __done_cb(self, child, context):
        self.done_signal.emit()


class CurrentActivityStep(Step):
    def get_hotspot_location(self):
        return 'current_activity', HotspotScale.NORMAL

    def bind_done_listeners(self):
        from jarabe import frame
        self._frame = frame.get_view()
        self._frame.hide_signal.connect(self.__done_cb)

    def unbind_done_listeners(self):
        self._frame.disconnect_by_func(self.__done_cb)

    def __done_cb(self, frame):
        self.done_signal.emit()


class ChangeZoomStep(Step):
    def __init__(self, zoom, *args, **kwargs):
        Step.__init__(self, *args, **kwargs)
        self._zoom = zoom

    def get_hotspot_location(self):
        return 'zoom#{}'.format(self._zoom), HotspotScale.NORMAL

    def bind_done_listeners(self):
        model = shell.get_model()
        model.zoom_level_changed.connect(self.__done_cb)

    def unbind_done_listeners(self):
        shell.get_model().zoom_level_changed.disconnect(self.__done_cb)

    def __done_cb(self, **kwargs):
        model = shell.get_model()
        if model.zoom_level == self._zoom:
            self.done_signal.emit()


class MeshSearchStep(Step):
    def get_hotspot_location(self):
        return 'desktop_search', HotspotScale.NORMAL

    def bind_done_listeners(self):
        entry = get_widget_registry().get('desktop_search')
        entry.connect('changed', self.__done_cb)

    def unbind_done_listeners(self):
        entry = get_widget_registry().get('desktop_search')
        entry.disconnect_by_func(self.__done_cb)

    def __done_cb(self, entry):
        self.done_signal.emit()
        entry.disconnect_by_func(self.__done_cb)


class MeshBuddyStep(Step):
    def get_hotspot_location(self):
        return 'mesh_buddy:latest', HotspotScale.NORMAL

    def bind_done_listeners(self):
        for widget in get_widget_registry().get_all('mesh_buddy#'):
            invoker = widget.props.palette_invoker
            invoker.connect('popup', self.__popup_cb)

    def unbind_done_listeners(self):
        for widget in get_widget_registry().get_all('mesh_buddy#'):
            invoker = widget.props.palette_invoker
            invoker.disconnect_by_func(self.__popup_cb)
            if invoker.props.palette is not None:
                try:
                    invoker.props.palette.disconnect_by_func(
                        self.__secondary_popup_cb)
                except TypeError:
                    pass  # Not bound

    def __popup_cb(self, invoker):
        invoker.props.palette.connect(
            'secondary-popup', self.__secondary_popup_cb)

    def __secondary_popup_cb(self, palette):
        self.done_signal.emit()


class OpenJournalStep(Step):
    def get_hotspot_location(self):
        return 'journal_icon', HotspotScale.NORMAL

    def bind_done_listeners(self):
        model = shell.get_model()
        model.connect('active-activity-changed', self.__done_cb)
        model.zoom_level_changed.connect(self.__zoom_cb)

    def unbind_done_listeners(self):
        model = shell.get_model()
        model.disconnect_by_func(self.__done_cb)
        model.zoom_level_changed.disconnect(self.__zoom_cb)

    def __zoom_cb(self, **kwargs):
        model = shell.get_model()
        if model.zoom_level == shell.ShellModel.ZOOM_ACTIVITY and \
           model.get_active_activity().is_journal():
            self.done_signal.emit()

    def __done_cb(self, model, activity):
        if activity.is_journal():
            self.done_signal.emit()


class JournalDetailsStep(Step):
    def get_hotspot_location(self):
        return 'journal_main_view', HotspotScale.NORMAL

    def bind_done_listeners(self):
        self._widget = get_widget_registry().get('journal_list_view')
        self._widget.connect('detail-clicked', self.__done_cb)

    def unbind_done_listeners(self):
        self._widget.disconnect_by_func(self.__done_cb)
        del self._widget

    def __done_cb(self, tree, obj):
        self.done_signal.emit()


class LaunchHelpStep(Step):
    def get_hotspot_location(self):
        return 'activity_icon#org.laptop.HelpActivity', HotspotScale.HELP_ICON

    def bind_done_listeners(self):
        model = shell.get_model()
        model.connect('launch-started', self.__launch_started_cb)

    def unbind_done_listeners(self):
        model = shell.get_model()
        model.disconnect_by_func(self.__launch_started_cb)

    def __launch_started_cb(self, model, activity):
        if activity.get_bundle_id() == 'org.laptop.HelpActivity':
            self.done_signal.emit()


class OwnerIconStep(Step):
    def get_hotspot_location(self):
        return 'owner_icon', HotspotScale.LARGE

    def bind_done_listeners(self):
        widget = get_widget_registry().get('owner_icon')
        self._invoker = widget.props.palette_invoker
        self._invoker.connect('popup', self.__popup_cb)

    def unbind_done_listeners(self):
        self._invoker.disconnect_by_func(self.__popup_cb)
        if self._invoker.props.palette is not None:
            try:
                self._invoker.props.palette.disconnect_by_func(
                    self.__secondary_popup_cb)
            except TypeError:
                pass  # Not bound
        del self._invoker

    def __popup_cb(self, invoker):
        invoker.props.palette.connect(
            'secondary-popup', self.__secondary_popup_cb, invoker)

    def __secondary_popup_cb(self, palette, invoker):
        self.done_signal.emit()


INITIAL_STEPS = [0]
STEPS = [
    ActivityIconHoverStep(  # 0
        _('Mouse-Over to Explore'),
        _('Move your pointer over the icon and wait to learn what it does.  '
          'Right click if you\'re in a hurry!'),
        _('Mouse over an activity icon to continue'),
        [1], image='onboard-activity-palette'),
    LaunchActivityStep(  # 1
        _('Make Something New'),
        _('Create a new %(activity name)s document or mouse over another '
          'activity icon and start it'),
        _('Press "Start new" (on any icon) to continue'),
        [2, 4, 14, 15], image='onboard-activity-palette-startnew'),
    ChangeTitleStep(  # 2
        'Title your Masterpiece',
        'Make it easy to find in the future with a descriptive title',
        'Open the activity toolbar and change the title to continue',
        [3], process=Processes.ACTIVITY, image='onboard-activity-title'),
    ChangeDescriptionStep(  # 3
        'Remember and Reflect',
        ('Store thoughts, ideas and reflections in the description field. '
         'View and search them later'),
        'Click to open the description and change it to continue',
        [], process=Processes.ACTIVITY, image='onboard-activity-description'),
    OpenFrameStep(  # 4
        'Navigate with the Frame',
        ('Pressing F6 (or moving your pointer into any corner) toggles '
         'the frame, which lets you navigate Sugar and control your computer'),
        'Explore another hotspot to continue', [5, 7, 8, 9, 12]),
    DragToClipboardStep(  # 5
        'Drag to the Clipboard',
        ('Drag text, images or anything else here to save it temporarily '
         'in your clipboard.  You can use Ctrl-C if you prefer'),
        'Put something on your clipboard to continue',
        [6], image='onboard-frame-drag-in'),
    DragFromClipboardStep(  # 6
        'Drag from the Clipboard',
        'Drag clipped items and use them in your activities',
        'Drag something from the clipboard to continue',
        [], image='onboard-frame-drag-out'),
    CurrentActivityStep(  # 7
        'Your Current Activity',
        ('The colored icons represent all the activities you have open. Just '
         'click to switch back'),
        'Click your current activity\'s icon to continue',
        [], image='onboard-frame-current-activity'),
    ChangeZoomStep(  # 8
        shell.ShellModel.ZOOM_HOME,
        'Zoom Back Home',
        'Click to zoom out to the home view to launch a new activity',
        'Go to the Home view to continue',
        [], image='onboard-frame-home-view'),
    ChangeZoomStep(  # 9
        shell.ShellModel.ZOOM_MESH, 'Zoom to the Neighbourhood',
        'View people nearby, shared activities and connect to WiFi networks',
        'Go to the Neighbourhood view to continue',
        [10, 11], image='onboard-frame-mesh-view'),
    MeshSearchStep(  # 10
        'Search for your WiFi network',
        'Find your WiFi network, then mouse over and press Connect',
        'Search for something to continue',
        [], image='onboard-wifi'),
    MeshBuddyStep(  # 11
        'Find your Friends in the Neighbourhood view',
        'Invite your buddies to join you and work collaboratively',
        _('Hover over a buddy and open their palette to continue'),
        [], image='onboard-buddy'),
    OpenJournalStep(  # 12
        'View and Search your Work',
        ('Find, remember and reflect on your work in the Journal. Copy it and'
         ' send it to buddies'),
        'Open the Journal to continue',
        [13], image='onboard-frame-journal'),
    JournalDetailsStep(  # 13
        'Reflect and Remember your Work',
        ('Press the details arrow to view a preview and write reflections '
         'and descriptions'),
        'Go to the details view to continue',
        [], image='onboard-journal-details'),
    LaunchHelpStep(  # 14
        _('Understand Your Computer with Helpful Guides'),
        _('Help activity houses many guides, covering Sugar and '
          'its activities'),
        _('Launch Help activity to continue'), []),
    OwnerIconStep(  # 15
        _('Control your Computer'),
        _('Shut down, restart or change settings on your '
          'computer by mousing over your XO icon'),
        _('Hover to open the palette to continue'),
        [], image='onboard-owner-icon')
]
