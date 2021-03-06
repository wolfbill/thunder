"""
Utilities for saving data
"""

import os
from math import isnan
from numpy import sum, shape, maximum, minimum, uint8, savetxt, size, save

from thunder.utils.common import checkParams


def arrayToImg(mat, filename, format="png"):
    """
    Write a 2D numpy array to a grayscale image.

    If mat is 3D, will separately write each image along the 3rd dimension.

    Parameters
    ----------
    mat : array (2D or 3D), dtype must be uint8
        Pixel values for image or set of images to write

    filename : str
        Base filename for writing

    format : str, optional, default = "png"
        Image format to write (see matplotlib's imsave for options)
    """
    from matplotlib.pyplot import imsave
    from matplotlib import cm

    dims = shape(mat)
    if len(dims) > 2:
        for z in range(0, dims[2]):
            cdata = mat[:, :, z]
            imsave(filename+"-"+str(z)+"."+format, cdata, cmap=cm.gray)
    elif len(dims) == 2:
        imsave(filename+"."+format, mat, cmap=cm.gray)
    else:
        raise NotImplementedError('array must be 2 or 3 dimensions for image writing')


def rescale(data):
    """
    Rescale data to lie between 0 and 255 and convert to uint8.

    For strictly positive data, subtract the min and divide by max
    otherwise, divide by the maximum absolute value and center

    If each element of data has multiple entries,
    they will be rescaled separately
    """
    if size(data.first()[1]) > 1:
        data = data.mapValues(lambda x: map(lambda y: 0 if isnan(y) else y, x))
    else:
        data = data.mapValues(lambda x: 0 if isnan(x) else x)
    mnVals = data.map(lambda (_, v): v).reduce(minimum)
    mxVals = data.map(lambda (_, v): v).reduce(maximum)
    if sum(mnVals < 0) == 0:
        data = data.mapValues(lambda x: uint8(255 * (x - mnVals)/(mxVals - mnVals)))
    else:
        mxVals = maximum(abs(mxVals), abs(mnVals))
        data = data.mapValues(lambda x: uint8(255 * ((x / (2 * mxVals)) + 0.5)))
    return data


def export(data, outputDirPath, outputFilename, outputFormat, sorting=False):
    """
    Export array data to a variety of local formats.

    Can export local arrays or a Series. If passed a Series,
    it will first be packed into one or more local arrrays.

    Parameters
    ----------
    data : Series, or numpy array
        The data to export

    outputDirPath : str
        Output directory

    outputFilename : str
        Output filename

    outputFormat : str
        Output format ("matlab", "npy", or "text")

    """
    from thunder.rdds.series import Series
    from scipy.io import savemat

    checkParams(outputFormat, ['matlab', 'npy', 'text'])

    if not os.path.exists(outputDirPath):
        os.makedirs(outputDirPath)

    filename = os.path.join(outputDirPath, outputFilename)

    def write(array, file, format, varname=None):
        if format == 'matlab':
            savemat(file+".mat", mdict={varname: array}, oned_as='column', do_compression='true')
        if format == 'npy':
            save(file, array)
        if format == 'text':
            savetxt(file+".txt", array, fmt="%.6f")

    if isinstance(data, Series):
        # force calculation of dimensions
        _tmp = data.dims
        if size(data.index) > 1:
            for ix in data.index:
                result = data.select(ix).pack(sorting=sorting)
                write(result, filename+"_"+str(ix), outputFormat, varname=outputFilename+"_"+str(ix))
        else:
            result = data.pack(sorting=sorting)
            write(result, filename, outputFormat, varname=outputFilename+"_"+str(data.index))
    else:
        write(data, filename, outputFormat, varname=outputFilename)
