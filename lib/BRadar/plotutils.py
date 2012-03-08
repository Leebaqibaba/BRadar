from matplotlib.colors import BoundaryNorm
from matplotlib.colorbar import ColorbarBase
import numpy as np		# using .ma for Masked Arrays, also for .isnan()
import matplotlib.pyplot as plt
import ctables		# for color table for reflectivities
from datetime import datetime, timedelta
from collections import OrderedDict
from matplotlib.animation import FuncAnimation
from BRadar.io import LoadRastRadar, RadarCache

def MakePPI(x, y, vals, norm, ref_table, ax=None, mask=None, 
            rasterized=False, meth='pcmesh', **kwargs):
    """
    Make a PPI plot at coordinates of *x*, *y* using *vals*.
    Colors are determined by the *norm* and *ref_table*.

    The function will automatically convert the *vals* array
    into a masked_array if there are NaNs and no *mask* is
    provided.

    *meth*      ['pc'|'pcmesh'|'im']
        Plotting method to use (pcolor, pcolormesh, imshow).
        pcolor() ('pc') works for the most generic case of arbitrary
        coordinates, but can be inefficient for regular domains.
        pcolormesh() ('pcmesh') can be more efficient, but assumes regular
        domains.
        imshow() ('im') is very efficient for rectilinear domains.

    Additional kwargs are passed to the plotting function.

    Returns the plotted object.

    """
    # It would be best if x and y were parallel arrays to vals.
    # I haven't tried to see what would happen if they were just 1-D arrays each...
    if ax is None :
        ax = plt.gca()

    if mask is None :
        mask = np.isnan(vals)

    # If vals is already a masked array, then the
    # final mask is the or'd of *mask* and the array's
    # existing mask.
    maskedVals = np.ma.masked_array(vals, mask=mask)
    
    #print(x.ndim, y.ndim)
    if meth == 'pc' :
        thePlot = ax.pcolor(x, y, maskedVals,
                        cmap=ref_table, norm=norm, **kwargs)
    elif meth == 'pcmesh' :
        thePlot = ax.pcolormesh(x, y, maskedVals,
                        cmap=ref_table, norm=norm, **kwargs)
    elif meth == 'im' :
        extent=(x.min(), x.max(), y.min(), y.max())
        thePlot = ax.imshow(maskedVals,
                        cmap=ref_table, norm=norm,
                        interpolation='none', origin='lower',
                        extent=extent,
                        **kwargs)
    else :
        raise ValueError("Invalid method for MakePPI: %s" % meth)

    thePlot.set_rasterized(rasterized)
    return thePlot



#--------------------------------------
#     Reflectivity
#--------------------------------------
# lut=-1 sets up discretized colormap, rather than smoothly changing colormap 
reflect_cmap = ctables.get_cmap("NWSRef", lut=-1)
reflect_cmap.set_over('0.25')
reflect_cmap.set_under('0.75')

NWS_Reflect = {'ref_table': reflect_cmap,
	           'norm': BoundaryNorm(np.arange(0, 80, 5),
               reflect_cmap.N, clip=False)}


def MakeReflectPPI(vals, lats, lons,
                   ax=None, cax=None,
                   axis_labels=True, colorbar=True, **kwargs) :
    # The Lats and Lons should be parallel arrays to vals.
    if ax is None :
       ax = plt.gca()

    thePlot = MakePPI(lons, lats, vals,
                      NWS_Reflect['norm'], NWS_Reflect['ref_table'],
                      ax=ax, **kwargs)

    # I am still not quite sure if this is the best place for this...
    if axis_labels : 
       ax.set_xlabel("Longitude [deg]")
       ax.set_ylabel("Latitude [deg]")

    if colorbar and cax is not None:
        MakeReflectColorbar(cax)

    return thePlot



def MakeReflectColorbar(ax=None, colorbarLabel="Reflectivity [dBZ]", **kwargs) :
    # Probably need a smarter way to allow fine-grained control of properties
    # like fontsize and such...
    if ax is None :
        ax = plt.gca()

    cbar = ColorbarBase(ax, cmap=NWS_Reflect['ref_table'],
                        norm=NWS_Reflect['norm'], **kwargs)
    cbar.set_label(colorbarLabel)
    return cbar


def TightBounds(lons, lats, vals) :
    badVals = np.isnan(vals)
    lats_masked = np.ma.masked_array(lats, mask=badVals)
    lons_masked = np.ma.masked_array(lons, mask=badVals)
    minLat = lats_masked.min()
    maxLat = lats_masked.max()
    minLon = lons_masked.min()
    maxLon = lons_masked.max()
    return {'minLat': minLat, 'minLon': minLon, 'maxLat': maxLat, 'maxLon': maxLon}


class RadarAnim(FuncAnimation) :
    def __init__(self, fig, files, load_func=None, robust=False,
                       sps=None, time_markers=None,
                       **kwargs) :
        """
        Create an animation object for viewing radar reflectivities.

        *fig*           matplotlib Figure object

        *files*         list of filenames containing the radar data

        *load_func*     The function to use to load the data from a file.
                        Must return a dictionary of 'vals' which contains
                        the 3D numpy array (T by Y by X), 'lats' and 'lons'.

                        It is also optional that the loading function also
                        provides a 'scan_time', either as a
                        :class:`datetime.datetime` object or as an integer
                        or a float representing the number of seconds since
                        UNIX Epoch.

        *robust*        Boolean (default: False) indicating whether or not
                        we can assume all the data will be for the same domain.
                        If you can't assume a consistant domain, then set
                        *robust* to True.  This often happens for PAR data.
                        Note that a robust rendering is slower.

        *sps*           The rate of data time for each second displayed.
                        Default: None (a data frame per display frame).

        *time_markers*  A list of time offsets (in seconds) for each frame.
                        If None, then autogenerate from the event_source
                        and data (unless *sps* is None).

        All other kwargs for :class:`FuncAnimation` are also allowed.

        To use, specify the axes to display the image on using
        :meth:`add_axes`. If no axes are added by draw time, then this class
        will use the current axes by default with no extra keywords.
        """
        #self._rd = files
        #self._loadfunc = load_func if load_func is not None else LoadRastRadar
        self._rd = RadarCache(files, cachewidth=3, load_func=load_func,
                              cyclable=True)

        self.startTime = self.curr_time
        self.endTime = self.prev_time

        self._ims = []
        self._im_kwargs = []
        self._new_axes = []
        #self._curr_time = None
        self._robust = robust
        frames = kwargs.pop('frames', None)
        #if len(files) < frames :
        #    raise ValueError("Not enough data files for the number of frames")
        self.time_markers = None
        FuncAnimation.__init__(self, fig, self.nextframe,
#                                     init_func=self.firstframe,
                                     **kwargs)

        self._sps = sps

        if time_markers is None :
            # Convert milliseconds per frame to frames per second
            self._fps = 1000.0 / self.event_source.interval
            if self._sps is not None :
                #timelen = (self.endTime - self.startTime)
                timestep = timedelta(0, self._sps / self._fps)

                currTime = self.startTime
                self.time_markers = [currTime]
                while currTime < self.endTime :
                    currTime += timestep
                    self.time_markers.append(currTime)
            else :
                # Don't even bother trying to make playback uniform.
                self.time_markers = None

        else :
            self.time_markers = time_markers
            self._fps = ((len(time_markers) - 1) /
                         ((self.time_markers[-1] -
                           self.time_markers[0]).total_seconds() / self._sps))
            self.event_source.interval = 1000.0 / self._fps
        self.save_count = (len(self.time_markers) if 
                           self.time_markers is not None else
                           len(self._rd))

    @property
    def curr_time(self) :
        """
        The :class:`datetime.datetime` object for the current frame's time.

        Could possibly be None.

        This is a read-only property.
        """
        return self._get_time(self._rd.curr())

    @property
    def prev_time(self) :
        """
        Similar to :meth:`curr_time`.
        """
        return self._get_time(self._rd.peek_prev())

    @property
    def next_time(self) :
        """
        Similar to :meth:`curr_time`.
        """
        return self._get_time(self._rd.peek_next())

    @staticmethod
    def _get_time(data) :
        currTime = data.get('scan_time', None)
        if (currTime is not None and
            not isinstance(currTime, datetime)) :
            currTime = datetime.utcfromtimestamp(currTime)

        return currTime

    def firstframe(self, *args) :
        #if len(self._ims) == 0 and len(self._new_axes) == 0 :
        #    self.add_axes(plt.gca())
        self._advance_anim()
        return self._ims

    def _advance_anim(self) :
        data = next(self._rd)

        if not self._robust :
            for im in self._ims :
                im.set_array(data['vals'][0, :-1, :-1].flatten())
        else :
            for im, kwargs in zip(self._ims, self._im_kwargs) :
                # Add this im object's axes object to _new_axes so
                # that a completely new rendering is made.
                self._new_axes.append((im.axes, kwargs))

                # Remove the current rendering from the Axes
                im.remove()

            # Reset these arrays so that they can be refilled
            self._ims = []
            self._im_kwargs = []

        for ax, kwargs in self._new_axes :
            self._im_kwargs.append(kwargs)
            self._ims.append(MakeReflectPPI(data['vals'][0],
                                            data['lats'], data['lons'],
                                            meth='pcmesh', axis_labels=False,
                                            mask=False, ax=ax, **kwargs))

        # Reset the "stack"
        self._new_axes = []


    def add_axes(self, ax, **kwargs) :
        """
        Display the animation on Axes *ax*. Can also specify what *kwargs* to
        pass to the call of :func:`MakeReflectPPI` except 'meth', 'axis_labels',
        'ax', and 'mask'.  Others such as 'zorder' and 'alpha' can be passed.
        """
        self._new_axes.append((ax, kwargs))

    def nextframe(self, frameindex, *args) :
        if self.time_markers is None :
            self._advance_anim()
            print "CurrTime:", str(self.curr_time)
            return self._ims

        frametime = self.time_markers[frameindex % self.save_count]

        if frametime > self.endTime :
            # We have no additional data to display.
            # Just simply hold until frametime cycles
            return None

        if frameindex % self.save_count == 0 and frameindex > 0 :
            # Force a cycling of the data
            while self.startTime < self.curr_time <= self.endTime :
                self._rd.next()
                print "Skipping ahead:", str(self.curr_time)

        if frametime >= self.curr_time :
            while self.next_time < frametime < self.endTime :
                # Dropping frames
                self._rd.next()
                print "Dropped:", str(self.curr_time)

            print "CurrTime:", str(self.curr_time)
            self._advance_anim()
            return self._ims
        else :
            return None


class RadarDisplay(object) :
    def __init__(self, ax, radarData, xs=None, ys=None) :
        """
        Create a display for radar data.
        """
        self.ax = ax
        self.radarData = radarData
        self._im = None
        self._title = None
        self._curr_time = None
        self.frameIndex = 0
        data = self.radarData.curr()
        self.xs = xs if xs is not None else data['lons']
        self.ys = ys if ys is not None else data['lats']
        self.refresh_display()

    def next(self) :
        if ((self.frameIndex + 1) <= (len(self.radarData) - 1)) :
            self.radarData.next()
            self.frameIndex += 1
            self.refresh_display()
        
    def prev(self) :
        if (0 <= (self.frameIndex - 1)) :
            self.radarData.prev()
            self.frameIndex -= 1
            self.refresh_display()

    def refresh_display(self) :
        """
        Draw the display using the current value of *self.radarData*.
        """
        data = self.radarData.curr()

        # Display current frame's radar image
        if self._im is None :
            self._im = MakeReflectPPI(data['vals'][0], self.ys, self.xs,
                                      meth='pcmesh', ax=self.ax,
                                      colorbar=False, axis_labels=False,
                                      zorder=0, mask=False)
        else :
            self._im.set_array(data['vals'][0, :-1, :-1].flatten())

        self._curr_time = data.get('scan_time', None)

        if (self._curr_time is not None and
            not isinstance(self._curr_time, datetime)) :
            self._curr_time = datetime.utcfromtimestamp(self._curr_time)

        if self._curr_time is not None :
            theDateTime = self._curr_time.strftime("%Y-%m-%d %H:%M:%S")
        else :
            theDateTime = 'Unknown Date/Time'

        # Update axis title label
        if self._title is None :
            self._title = self.ax.set_title(theDateTime)
        else :
            self._title.set_text(theDateTime)

class BaseControlSys(object) :
    def __init__(self, fig, rd) :
        """
        Create a control system for paging radar frames.

        *fig*
            The matplotlib figure object.

        *rd*
            The RadarDisplay object
        """
        self.fig = fig
        self.rd = rd

        fig.canvas.mpl_connect('key_press_event', self.process_key)
        #fig.canvas.mpl_connect('button_release_event',
        #                       self.process_click)


        self.keymap = OrderedDict()
        self.keymap['left'] = {'func': self.step_back,
                               'help': "Step back display by one frame"}
        self.keymap['right'] = {'func': self.step_forward,
                                'help': 'Step forward display by one frame'}

        self._clean_mplkeymap()


    def _clean_mplkeymap(self) :
        from matplotlib import rcParams
        # TODO: Generalize this
        # Need to remove some keys...
        rcParams['keymap.fullscreen'] = []
        rcParams['keymap.zoom'] = []
        rcParams['keymap.save'] = []
        for keymap in ('keymap.home', 'keymap.back', 'keymap.forward') :
            for key in self.keymap :
                if key in rcParams[keymap] :
                    rcParams[keymap].remove(key)

    def process_key(self, event) :
        """
        Key-press handler
        """
        if event.key in self.keymap :
            self.keymap[event.key]['func']()
            self.fig.canvas.draw_idle()

    def step_back(self) :
        self.rd.prev()

    def step_forward(self) :
        self.rd.next()


