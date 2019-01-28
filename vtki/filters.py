"""
These classes hold methods to apply general filters to any data type.
By inherritting these classes into the wrapped VTK data structures, a user
can easily apply common filters in an intuitive manner.

Example
-------

>>> import vtki
>>> from vtki import examples
>>> dataset = examples.load_uniform()

>>> # Threshold
>>> thresh = dataset.threshold([100, 500])

>>> # Slice
>>> slc = dataset.slice()

>>> # Clip
>>> clp = dataset.clip(invert=True)

>>> # Contour
>>> iso = dataset.contour()

"""
import collections
import logging
import numpy as np
import vtk

import vtki
from vtki.utilities import get_scalar, wrap, is_inside_bounds

NORMALS = {
    'x': [1, 0, 0],
    'y': [0, 1, 0],
    'z': [0, 0, 1],
    '-x': [-1, 0, 0],
    '-y': [0, -1, 0],
    '-z': [0, 0, -1],
}


def _get_output(algorithm, iport=0, iconnection=0, oport=0, active_scalar=None,
                active_scalar_field='point'):
    """A helper to get the algorithm's output and copy input's vtki meta info"""
    ido = algorithm.GetInputDataObject(iport, iconnection)
    data = wrap(algorithm.GetOutputDataObject(oport))
    data.copy_meta_from(ido)
    if active_scalar is not None:
        data.set_active_scalar(active_scalar, preference=active_scalar_field)
    return data


def _generate_plane(normal, origin):
    """ Returns a vtk.vtkPlane """
    plane = vtk.vtkPlane()
    plane.SetNormal(normal[0], normal[1], normal[2])
    plane.SetOrigin(origin[0], origin[1], origin[2])
    return plane



class DataSetFilters(object):
    """A set of common filters that can be applied to any vtkDataSet"""


    def clip(dataset, normal='x', origin=None, invert=True):
        """
        Clip a dataset by a plane by specifying the origin and normal. If no
        parameters are given the clip will occur in the center of that dataset

        Parameters
        ----------
        normal : tuple(float) or str
            Length 3 tuple for the normal vector direction. Can also be
            specified as a string conventional direction such as ``'x'`` for
            ``(1,0,0)`` or ``'-x'`` for ``(-1,0,0)``, etc.

        origin : tuple(float)
            The center ``(x,y,z)`` coordinate of the plane on which the clip
            occurs

        invert : bool
            Flag on whether to flip/invert the clip

        """
        if isinstance(normal, str):
            normal = NORMALS[normal.lower()]
        # find center of data if origin not specified
        if origin is None:
            origin = dataset.center
        # create the plane for clipping
        plane = _generate_plane(normal, origin)
        # run the clip
        alg = vtk.vtkClipDataSet()
        alg.SetInputDataObject(dataset) # Use the grid as the data we desire to cut
        alg.SetClipFunction(plane) # the the cutter to use the plane we made
        alg.SetInsideOut(invert) # invert the clip if needed
        alg.Update() # Perfrom the Cut
        return _get_output(alg)


    def slice(dataset, normal='x', origin=None, generate_triangles=False):
        """Slice a dataset by a plane at the specified origin and normal vector
        orientation. If no origin is specified, the center of the input dataset will
        be used.

        Parameters
        ----------
        normal : tuple(float) or str
            Length 3 tuple for the normal vector direction. Can also be
            specified as a string conventional direction such as ``'x'`` for
            ``(1,0,0)`` or ``'-x'`` for ``(-1,0,0)```, etc.

        origin : tuple(float)
            The center (x,y,z) coordinate of the plane on which the slice occurs

        generate_triangles: bool, optional
            If this is enabled (``False`` by default), the output will be
            triangles otherwise, the output will be the intersection polygons.

        """
        if isinstance(normal, str):
            normal = NORMALS[normal.lower()]
        # find center of data if origin not specified
        if origin is None:
            origin = dataset.center
        if not is_inside_bounds(origin, dataset.bounds):
            raise AssertionError('Slice is outside data bounds.')
        # create the plane for clipping
        plane = _generate_plane(normal, origin)
        # create slice
        alg = vtk.vtkCutter() # Construct the cutter object
        alg.SetInputDataObject(dataset) # Use the grid as the data we desire to cut
        alg.SetCutFunction(plane) # the the cutter to use the plane we made
        if not generate_triangles:
            alg.GenerateTrianglesOff()
        alg.Update() # Perfrom the Cut
        return _get_output(alg)


    def slice_orthogonal(dataset, x=None, y=None, z=None, generate_triangles=False):
        """Creates three orthogonal slices through the dataset on the three
        caresian planes. Yields a MutliBlock dataset of the three slices

        Parameters
        ----------
        x : float
            The X location of the YZ slice

        y : float
            The Y location of the XZ slice

        z : float
            The Z location of the XY slice

        generate_triangles: bool, optional
            If this is enabled (``False`` by default), the output will be
            triangles otherwise, the output will be the intersection polygons.

        """
        output = vtki.MultiBlock()
        # Create the three slices
        if x is None:
            x = dataset.center[0]
        if y is None:
            y = dataset.center[1]
        if z is None:
            z = dataset.center[2]
        output[0, 'YZ'] = dataset.slice(normal='x', origin=[x,y,z], generate_triangles=generate_triangles)
        output[1, 'XZ'] = dataset.slice(normal='y', origin=[x,y,z], generate_triangles=generate_triangles)
        output[2, 'XY'] = dataset.slice(normal='z', origin=[x,y,z], generate_triangles=generate_triangles)
        return output


    def slice_along_axis(dataset, n=5, axis='x', tolerance=None, generate_triangles=False):
        """Create many slices of the input dataset along a specified axis.

        Parameters
        ----------
        n : int
            The number of slices to create

        axis : str or int
            The axis to generate the slices along. Perpendicular to the slices.
            Can be string name (``'x'``, ``'y'``, or ``'z'``) or axis index
            (``0``, ``1``, or ``2``).

        tolerance : float, optional
            The toleranceerance to the edge of the dataset bounds to create the slices

        generate_triangles: bool, optional
            If this is enabled (``False`` by default), the output will be
            triangles otherwise, the output will be the intersection polygons.

        """
        output = vtki.MultiBlock()
        if isinstance(axis, str):
            axes = {'x':0, 'y':1, 'z':2}
            try:
                ax = axes[axis]
            except KeyError:
                raise RuntimeError('Axis ({}) not understood'.format(axis))
        else:
            ax = axis
        # get the locations along that axis
        if tolerance is None:
            tolerance = (dataset.bounds[ax*2+1] - dataset.bounds[ax*2]) * 0.01
        rng = np.linspace(dataset.bounds[ax*2]+tolerance, dataset.bounds[ax*2+1]-tolerance, n)
        center = list(dataset.center)
        # Make each of the slices
        for i in range(n):
            center[ax] = rng[i]
            slc = DataSetFilters.slice(dataset, normal=axis, origin=center, generate_triangles=generate_triangles)
            output[i, 'slice%.2d'%i] = slc
        return output


    def threshold(dataset, value=None, scalars=None, invert=False, continuous=False,
                  preference='cell'):
        """
        This filter will apply a ``vtkThreshold`` filter to the input dataset and
        return the resulting object. This extracts cells where scalar value in each
        cell satisfies threshold criterion.  If scalars is None, the inputs
        active_scalar is used.

        Parameters
        ----------
        value : float or iterable, optional
            Single value or (min, max) to be used for the data threshold.  If
            iterable, then length must be 2. If no value is specified, the
            non-NaN data range will be used to remove any NaN values.

        scalars : str, optional
            Name of scalars to threshold on. Defaults to currently active scalars.

        invert : bool, optional
            If value is a single value, when invert is True cells are kept when
            their values are below parameter "value".  When invert is False
            cells are kept when their value is above the threshold "value".
            Default is False: yielding above the threshold "value".

        continuous : bool, optional
            When True, the continuous interval [minimum cell scalar,
            maxmimum cell scalar] will be used to intersect the threshold bound,
            rather than the set of discrete scalar values from the vertices.

        preference : str, optional
            When scalars is specified, this is the perfered scalar type to search
            for in the dataset.  Must be either 'point' or 'cell'.

        """
        # set the scalaras to threshold on
        if scalars is None:
            field, scalars = dataset.active_scalar_info
        arr, field = get_scalar(dataset, scalars, preference=preference, info=True)

        if arr is None:
            raise AssertionError('No arrays present to threshold.')

        # If using an inverted range, merge the result of two fitlers:
        if isinstance(value, collections.Iterable) and invert:
            valid_range = [np.nanmin(arr), np.nanmax(arr)]
            # Create two thresholds
            t1 = dataset.threshold([valid_range[0], value[0]], scalars=scalars,
                    continuous=continuous, preference=preference, invert=False)
            t2 = dataset.threshold([value[1], valid_range[1]], scalars=scalars,
                    continuous=continuous, preference=preference, invert=False)
            # Use an AppendFilter to merge the two results
            appender = vtk.vtkAppendFilter()
            appender.AddInputData(t1)
            appender.AddInputData(t2)
            appender.Update()
            return _get_output(appender)

        # Run a standard threshold algorithm
        alg = vtk.vtkThreshold()
        alg.SetInputDataObject(dataset)
        alg.SetInputArrayToProcess(0, 0, 0, field, scalars) # args: (idx, port, connection, field, name)
        # set thresholding parameters
        alg.SetUseContinuousCellRange(continuous)
        # use valid range if no value given
        if value is None:
            value = dataset.get_data_range(scalars)
        # check if value is iterable (if so threshold by min max range like ParaView)
        if isinstance(value, collections.Iterable):
            if len(value) != 2:
                raise AssertionError('Value range must be length one for a float value or two for min/max; not ({}).'.format(value))
            alg.ThresholdBetween(value[0], value[1])
        else:
            # just a single value
            if invert:
                alg.ThresholdByLower(value)
            else:
                alg.ThresholdByUpper(value)
        # Run the threshold
        alg.Update()
        return _get_output(alg)


    def threshold_percent(dataset, percent=0.50, scalars=None, invert=False,
                          continuous=False, preference='cell'):
        """Thresholds the dataset by a percentage of its range on the active
        scalar array or as specified

        Parameters
        ----------
        percent : float or tuple(float), optional
            The percentage (0,1) to threshold. If value is out of 0 to 1 range,
            then it will be divided by 100 and checked to be in that range.

        scalars : str, optional
            Name of scalars to threshold on. Defaults to currently active scalars.

        invert : bool, optional
            When invert is True cells are kept when their values are below the
            percentage of the range.  When invert is False, cells are kept when
            their value is above the percentage of the range.
            Default is False: yielding above the threshold "value".

        continuous : bool, optional
            When True, the continuous interval [minimum cell scalar,
            maxmimum cell scalar] will be used to intersect the threshold bound,
            rather than the set of discrete scalar values from the vertices.

        preference : str, optional
            When scalars is specified, this is the perfered scalar type to search
            for in the dataset.  Must be either 'point' or 'cell'.

        """
        if scalars is None:
            field, tscalars = dataset.active_scalar_info
        else:
            tscalars = scalars
        dmin, dmax = dataset.get_data_range(arr=tscalars, preference=preference)

        def _check_percent(percent):
            """Make sure percent is between 0 and 1 or fix if between 0 and 100."""
            if percent >= 1:
                percent = float(percent) / 100.0
                if percent > 1:
                    raise RuntimeError('Percentage ({}) is out of range (0, 1).'.format(percent))
            if percent < 1e-10:
                raise RuntimeError('Percentage ({}) is too close to zero or negative.'.format(percent))
            return percent

        def _get_val(percent, dmin, dmax):
            """Gets the value from a percentage of a range"""
            percent = _check_percent(percent)
            return dmin + float(percent) * (dmax - dmin)

        # Compute the values
        if isinstance(percent, collections.Iterable):
            # Get two values
            value = [_get_val(percent[0], dmin, dmax), _get_val(percent[1], dmin, dmax)]
        else:
            # Compute one value to threshold
            value = _get_val(percent, dmin, dmax)
        # Use the normal thresholding function on these values
        return DataSetFilters.threshold(dataset, value=value, scalars=scalars,
                    invert=invert, continuous=continuous, preference=preference)


    def outline(dataset, generate_faces=False):
        """Produces an outline of the full extent for the input dataset.

        Parameters
        ----------
        generate_faces : bool, optional
            Generate solid faces for the box. This is off by default

        """
        alg = vtk.vtkOutlineFilter()
        alg.SetInputDataObject(dataset)
        alg.SetGenerateFaces(generate_faces)
        alg.Update()
        return wrap(alg.GetOutputDataObject(0))

    def outline_corners(dataset, factor=0.2):
        """Produces an outline of the corners for the input dataset.

        Parameters
        ----------
        factor : float, optional
            controls the relative size of the corners to the length of the
            corresponding bounds

        """
        alg = vtk.vtkOutlineCornerFilter()
        alg.SetInputDataObject(dataset)
        alg.SetCornerFactor(factor)
        alg.Update()
        return wrap(alg.GetOutputDataObject(0))

    def extract_geometry(dataset):
        """Extract the outer surface of a volume or structured grid dataset as
        PolyData. This will extract all 0D, 1D, and 2D cells producing the
        boundary faces of the dataset.
        """
        alg = vtk.vtkGeometryFilter()
        alg.SetInputDataObject(dataset)
        alg.Update()
        return _get_output(alg)

    def wireframe(dataset):
        """Extract all the internal/external edges of the dataset as PolyData.
        This produces a full wireframe representation of the input dataset.
        """
        alg = vtk.vtkExtractEdges()
        alg.SetInputDataObject(dataset)
        alg.Update()
        return _get_output(alg)


    def elevation(dataset, low_point=None, high_point=None, scalar_range=None,
                  preference='point', set_active=True):
        """Generate scalar values on a dataset.  The scalar values lie within a
        user specified range, and are generated by computing a projection of
        each dataset point onto a line.
        The line can be oriented arbitrarily.
        A typical example is to generate scalars based on elevation or height
        above a plane.

        Parameters
        ----------
        low_point : tuple(float), optional
            The low point of the projection line in 3D space. Default is bottom
            center of the dataset. Otherwise pass a length 3 tuple(float).

        high_point : tuple(float), optional
            The high point of the projection line in 3D space. Default is top
            center of the dataset. Otherwise pass a length 3 tuple(float).

        scalar_range : str or tuple(float), optional
            The scalar range to project to the low and high points on the line
            that will be mapped to the dataset. If None given, the values will
            be computed from the elevation (Z component) range between the
            high and low points. Min and max of a range can be given as a length
            2 tuple(float). If ``str`` name of scalara array present in the
            dataset given, the valid range of that array will be used.

        preference : str, optional
            When a scalar name is specified for ``scalar_range``, this is the
            perfered scalar type to search for in the dataset.
            Must be either 'point' or 'cell'.

        set_active : bool, optional
            A boolean flag on whethter or not to set the new `Elevation` scalar
            as the active scalar array on the output dataset.

        Warning
        -------
        This will create a scalar array named `Elevation` on the point data of
        the input dataset and overwrite an array named `Elevation` if present.

        """
        # Fix the projection line:
        if low_point is None:
            low_point = list(dataset.center)
            low_point[2] = dataset.bounds[4]
        if high_point is None:
            high_point = list(dataset.center)
            high_point[2] = dataset.bounds[5]
        # Fix scalar_range:
        if scalar_range is None:
            scalar_range = (low_point[2], high_point[2])
        elif isinstance(scalar_range, str):
            scalar_range = dataset.get_data_range(arr=scalar_range, preference=preference)
        elif isinstance(scalar_range, collections.Iterable):
            assert len(scalar_range) == 2, 'scalar_range must have a length of two defining the min and max'
        else:
            raise RuntimeError('scalar_range argument ({}) not understood.'.format(type(scalar_range)))
        # Construct the filter
        alg = vtk.vtkElevationFilter()
        alg.SetInputDataObject(dataset)
        # Set the parameters
        alg.SetScalarRange(scalar_range)
        alg.SetLowPoint(low_point)
        alg.SetHighPoint(high_point)
        alg.Update()
        # Decide on updating active scalar array
        name = 'Elevation' # Note that this is added to the PointData
        if not set_active:
            name = None
        return _get_output(alg, active_scalar=name, active_scalar_field='point')


    def contour(dataset, isosurfaces=10, scalars=None, compute_normals=False,
                compute_gradients=False, compute_scalars=True, preference='point'):
        """Contours an input dataset by an array. ``isosurfaces`` can be an integer
        specifying the number of isosurfaces in the data range or an iterable set of
        values for explicitly setting the isosurfaces.

        Parameters
        ----------
        isosurfaces : int or iterable
            Number of isosurfaces to compute across valid data range or an
            iterable of float values to explicitly use as the isosurfaces.

        scalars : str, optional
            Name of scalars to threshold on. Defaults to currently active scalars.

        compute_normals : bool, optional

        compute_gradients : bool, optional
            Desc

        compute_scalars : bool, optional
            Preserves the scalar values that are being contoured

        preference : str, optional
            When scalars is specified, this is the perfered scalar type to search
            for in the dataset.  Must be either 'point' or 'cell'.

        """
        # Make sure the input has scalars to contour on
        if dataset.n_scalars < 1:
            raise AssertionError('Input dataset for the contour filter must have scalar data.')
        alg = vtk.vtkContourFilter()
        alg.SetInputDataObject(dataset)
        alg.SetComputeNormals(compute_normals)
        alg.SetComputeGradients(compute_gradients)
        alg.SetComputeScalars(compute_scalars)
        # set the array to contour on
        if scalars is None:
            field, scalars = dataset.active_scalar_info
        else:
            _, field = get_scalar(dataset, scalars, preference=preference, info=True)
        # NOTE: only point data is allowed? well cells works but seems buggy?
        if field != 0:
            raise AssertionError('Contour filter only works on Point data. Array ({}) is in the Cell data.'.format(scalars))
        alg.SetInputArrayToProcess(0, 0, 0, field, scalars) # args: (idx, port, connection, field, name)
        # set the isosurfaces
        if isinstance(isosurfaces, int):
            # generate values
            alg.GenerateValues(isosurfaces, dataset.get_data_range(scalars))
        elif isinstance(isosurfaces, collections.Iterable):
            alg.SetNumberOfContours(len(isosurfaces))
            for i, val in enumerate(isosurfaces):
                alg.SetValue(i, val)
        else:
            raise RuntimeError('isosurfaces not understood.')
        alg.Update()
        return _get_output(alg)


    def texture_map_to_plane(dataset, origin, point_u, point_v, inplace=False,
                             name='Texture Coordinates'):
        """Texture map this dataset to a user defined plane. This is often used
        to define a plane to texture map an image to this dataset. The plane
        defines the spatial reference and extent of that image.

        Parameters
        ----------
        origin : tuple(float)
            Length 3 iterable of floats defining the XYZ coordinates of the
            BOTTOM LEFT CORNER of the plane

        point_u : tuple(float)
            Length 3 iterable of floats defining the XYZ coordinates of the
            BOTTOM RIGHT CORNER of the plane

        point_v : tuple(float)
            Length 3 iterable of floats defining the XYZ coordinates of the
            TOP LEFT CORNER of the plane

        inplace : bool, optional
            If True, the new texture coordinates will be added to the dataset
            inplace. If False (default), a new dataset is returned with the
            textures coordinates

        name : str, optional
            The string name to give the new texture coordinates if applying
            the filter inplace.

        """
        alg = vtk.vtkTextureMapToPlane()
        alg.SetOrigin(origin) # BOTTOM LEFT CORNER
        alg.SetPoint1(point_u) # BOTTOM RIGHT CORNER
        alg.SetPoint2(point_v) # TOP LEFT CORNER
        alg.SetInputDataObject(dataset)
        alg.Update()
        output = _get_output(alg)
        if not inplace:
            return output
        t_coords = output.GetPointData().GetTCoords()
        t_coords.SetName(name)
        otc = dataset.GetPointData().GetTCoords()
        dataset.GetPointData().SetTCoords(t_coords)
        dataset.GetPointData().AddArray(t_coords)
        # CRITICAL:
        dataset.GetPointData().AddArray(otc) # Add old ones back at the end
        return # No return type because it is inplace