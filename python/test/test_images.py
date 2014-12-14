import glob
import struct
import os
from numpy import allclose, arange, array, array_equal, dtype, prod, vstack, zeros
import itertools
from nose.tools import assert_equals, assert_raises, assert_true
import unittest

from thunder.rdds.fileio.imagesloader import ImagesLoader
from thunder.rdds.fileio.seriesloader import SeriesLoader
from thunder.rdds.imgblocks.strategy import PaddedBlockingStrategy, SimpleBlockingStrategy
from test_utils import PySparkTestCase, PySparkTestCaseWithOutputDir

_have_image = False
try:
    from PIL import Image
    _have_image = True
except ImportError:
    # PIL not available; skip tests that require it
    Image = None


def _generate_test_arrays(narys, dtype_='int16'):
    sh = 4, 3, 3
    sz = prod(sh)
    arys = [arange(i, i+sz, dtype=dtype(dtype_)).reshape(sh) for i in xrange(0, sz * narys, sz)]
    return arys, sh, sz


def findSourceTreeDir(dirname="utils/data"):
    testdirpath = os.path.dirname(os.path.realpath(__file__))
    testresourcesdirpath = os.path.join(testdirpath, "..", "thunder", dirname)
    if not os.path.isdir(testresourcesdirpath):
        raise IOError("Directory "+testresourcesdirpath+" not found")
    return testresourcesdirpath


class TestImages(PySparkTestCase):

    def evaluate_series(self, arys, series, sz):
        assert_equals(sz, len(series))
        for serieskey, seriesval in series:
            expectedval = array([ary[serieskey] for ary in arys], dtype='int16')
            assert_true(array_equal(expectedval, seriesval))

    def test_castToFloat(self):
        arys, shape, size = _generate_test_arrays(2, 'uint8')
        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        castdata = imagedata.astype("smallfloat")

        assert_equals('float16', str(castdata.dtype))
        assert_equals('float16', str(castdata.first()[1].dtype))

    def test_toSeries(self):
        # create 3 arrays of 4x3x3 images (C-order), containing sequential integers
        narys = 3
        arys, sh, sz = _generate_test_arrays(narys)

        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        series = imagedata.toBlocks((4, 1, 1)).toSeries().collect()

        self.evaluate_series(arys, series, sz)

    def test_toSeriesWithPack(self):
        ary = arange(8, dtype=dtype('int16')).reshape((2, 4))

        image = ImagesLoader(self.sc).fromArrays(ary)
        series = image.toBlocks("150M").toSeries()

        seriesvals = series.collect()
        seriesary = series.pack()
        seriesary_xpose = series.pack(transpose=True)

        # check ordering of keys
        assert_equals((0, 0), seriesvals[0][0])  # first key
        assert_equals((1, 0), seriesvals[1][0])  # second key
        assert_equals((0, 1), seriesvals[2][0])
        assert_equals((1, 1), seriesvals[3][0])
        assert_equals((0, 2), seriesvals[4][0])
        assert_equals((1, 2), seriesvals[5][0])
        assert_equals((0, 3), seriesvals[6][0])
        assert_equals((1, 3), seriesvals[7][0])

        # check dimensions tuple matches numpy shape
        assert_equals(image.dims.count, series.dims.count)
        assert_equals(ary.shape, series.dims.count)

        # check that values are in Fortran-convention order
        collectedvals = array([kv[1] for kv in seriesvals], dtype=dtype('int16')).ravel()
        assert_true(array_equal(ary.ravel(order='F'), collectedvals))

        # check that packing returns original array
        assert_true(array_equal(ary, seriesary))
        assert_true(array_equal(ary.T, seriesary_xpose))

    def test_threeDArrayToSeriesWithPack(self):
        ary = arange(24, dtype=dtype('int16')).reshape((3, 4, 2))

        image = ImagesLoader(self.sc).fromArrays(ary)
        series = image.toBlocks("150M").toSeries()

        seriesvals = series.collect()
        seriesary = series.pack()
        seriesary_xpose = series.pack(transpose=True)

        # check ordering of keys
        assert_equals((0, 0, 0), seriesvals[0][0])  # first key
        assert_equals((1, 0, 0), seriesvals[1][0])  # second key
        assert_equals((2, 0, 0), seriesvals[2][0])
        assert_equals((0, 1, 0), seriesvals[3][0])
        assert_equals((1, 1, 0), seriesvals[4][0])
        assert_equals((2, 1, 0), seriesvals[5][0])
        assert_equals((0, 2, 0), seriesvals[6][0])
        assert_equals((1, 2, 0), seriesvals[7][0])
        assert_equals((2, 2, 0), seriesvals[8][0])
        assert_equals((0, 3, 0), seriesvals[9][0])
        assert_equals((1, 3, 0), seriesvals[10][0])
        assert_equals((2, 3, 0), seriesvals[11][0])
        assert_equals((0, 0, 1), seriesvals[12][0])
        assert_equals((1, 0, 1), seriesvals[13][0])
        assert_equals((2, 0, 1), seriesvals[14][0])
        assert_equals((0, 1, 1), seriesvals[15][0])
        assert_equals((1, 1, 1), seriesvals[16][0])
        assert_equals((2, 1, 1), seriesvals[17][0])
        assert_equals((0, 2, 1), seriesvals[18][0])
        assert_equals((1, 2, 1), seriesvals[19][0])
        assert_equals((2, 2, 1), seriesvals[20][0])
        assert_equals((0, 3, 1), seriesvals[21][0])
        assert_equals((1, 3, 1), seriesvals[22][0])
        assert_equals((2, 3, 1), seriesvals[23][0])

        # check dimensions tuple matches numpy shape
        assert_equals(ary.shape, series.dims.count)

        # check that values are in Fortran-convention order
        collectedvals = array([kv[1] for kv in seriesvals], dtype=dtype('int16')).ravel()
        assert_true(array_equal(ary.ravel(order='F'), collectedvals))

        # check that packing returns transpose of original array
        assert_true(array_equal(ary, seriesary))
        assert_true(array_equal(ary.T, seriesary_xpose))

    def _run_tst_toSeriesWithSplitsAndPack(self, strategy):
        ary = arange(8, dtype=dtype('int16')).reshape((4, 2))

        image = ImagesLoader(self.sc).fromArrays(ary)
        series = image.toBlocks(strategy).toSeries()

        seriesvals = series.collect()
        seriesary = series.pack()

        # check ordering of keys
        assert_equals((0, 0), seriesvals[0][0])  # first key
        assert_equals((1, 0), seriesvals[1][0])  # second key
        assert_equals((2, 0), seriesvals[2][0])
        assert_equals((3, 0), seriesvals[3][0])
        assert_equals((0, 1), seriesvals[4][0])
        assert_equals((1, 1), seriesvals[5][0])
        assert_equals((2, 1), seriesvals[6][0])
        assert_equals((3, 1), seriesvals[7][0])

        # check dimensions tuple matches numpy shape
        assert_equals(ary.shape, series.dims.count)

        # check that values are in Fortran-convention order
        collectedvals = array([kv[1] for kv in seriesvals], dtype=dtype('int16')).ravel()
        assert_true(array_equal(ary.ravel(order='F'), collectedvals))

        # check that packing returns original array
        assert_true(array_equal(ary, seriesary))

    def test_toSeriesWithSplitsAndPack(self):
        strategy = SimpleBlockingStrategy((1, 2))
        self._run_tst_toSeriesWithSplitsAndPack(strategy)

    def test_toSeriesWithPaddedSplitsAndPack(self):
        strategy = PaddedBlockingStrategy((1, 2), padding=(1, 1))
        self._run_tst_toSeriesWithSplitsAndPack(strategy)

    def test_toSeriesWithInefficientSplitAndSortedPack(self):
        ary = arange(8, dtype=dtype('int16')).reshape((4, 2))

        image = ImagesLoader(self.sc).fromArrays(ary)
        series = image.toBlocks((2, 1)).toSeries()

        seriesvals = series.collect()
        seriesary = series.pack(sorting=True)

        # check ordering of keys
        assert_equals((0, 0), seriesvals[0][0])  # first key
        assert_equals((1, 0), seriesvals[1][0])  # second key
        assert_equals((0, 1), seriesvals[2][0])
        assert_equals((1, 1), seriesvals[3][0])
        # end of first block
        # beginning of second block
        assert_equals((2, 0), seriesvals[4][0])
        assert_equals((3, 0), seriesvals[5][0])
        assert_equals((2, 1), seriesvals[6][0])
        assert_equals((3, 1), seriesvals[7][0])

        # check dimensions tuple matches numpy shape
        assert_equals(ary.shape, series.dims.count)

        # check that values are in expected order
        collectedvals = array([kv[1] for kv in seriesvals], dtype=dtype('int16')).ravel()
        assert_true(array_equal(ary[:2, :].ravel(order='F'), collectedvals[:4]))  # first block
        assert_true(array_equal(ary[2:4, :].ravel(order='F'), collectedvals[4:]))  # second block

        # check that packing returns original array (after sort)
        assert_true(array_equal(ary, seriesary))

    def test_toBlocksWithSplit(self):
        ary = arange(8, dtype=dtype('int16')).reshape((2, 4))

        image = ImagesLoader(self.sc).fromArrays(ary)
        groupedblocks = image.toBlocks((1, 2))

        # collectedblocks = blocks.collect()
        collectedgroupedblocks = groupedblocks.collect()
        assert_equals((0, 0), collectedgroupedblocks[0][0].spatialKey)
        assert_true(array_equal(ary[:, :2].ravel(), collectedgroupedblocks[0][1].ravel()))
        assert_equals((0, 2), collectedgroupedblocks[1][0].spatialKey)
        assert_true(array_equal(ary[:, 2:].ravel(), collectedgroupedblocks[1][1].ravel()))

    def test_toSeriesBySlices(self):
        narys = 3
        arys, sh, sz = _generate_test_arrays(narys)

        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        imagedata.cache()

        test_params = [
            (1, 1, 1), (1, 1, 2), (1, 1, 3), (1, 2, 1), (1, 2, 2), (1, 2, 3),
            (1, 3, 1), (1, 3, 2), (1, 3, 3),
            (2, 1, 1), (2, 1, 2), (2, 1, 3), (2, 2, 1), (2, 2, 2), (2, 2, 3),
            (2, 3, 1), (2, 3, 2), (2, 3, 3)]
        for bpd in test_params:
            series = imagedata.toBlocks(bpd).toSeries().collect()

            self.evaluate_series(arys, series, sz)

    def _run_tst_roundtripThroughBlocks(self, strategy):
        imagepath = findSourceTreeDir("utils/data/fish/tif-stack")
        images = ImagesLoader(self.sc).fromMultipageTif(imagepath)
        blockedimages = images.toBlocks(strategy)
        recombinedimages = blockedimages.toImages()

        collectedimages = images.collect()
        roundtrippedimages = recombinedimages.collect()
        for orig, roundtripped in zip(collectedimages, roundtrippedimages):
            assert_true(array_equal(orig[1], roundtripped[1]))

    def test_roundtripThroughBlocks(self):
        strategy = SimpleBlockingStrategy((2, 2, 2))
        self._run_tst_roundtripThroughBlocks(strategy)

    def test_roundtripThroughPaddedBlocks(self):
        strategy = PaddedBlockingStrategy((2, 2, 2), padding=2)
        self._run_tst_roundtripThroughBlocks(strategy)


class TestImagesStats(PySparkTestCase):
    def test_mean(self):
        from test_utils import elementwise_mean
        arys, shape, size = _generate_test_arrays(2, 'uint8')
        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        meanval = imagedata.mean()

        expected = elementwise_mean(arys).astype('float16')
        assert_true(allclose(expected, meanval))
        assert_equals('float16', str(meanval.dtype))

    def test_sum(self):
        from numpy import add
        arys, shape, size = _generate_test_arrays(2, 'uint8')
        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        sumval = imagedata.sum(dtype='uint32')

        arys = [ary.astype('uint32') for ary in arys]
        expected = reduce(add, arys)
        assert_true(array_equal(expected, sumval))
        assert_equals('uint32', str(sumval.dtype))

    def test_variance(self):
        from test_utils import elementwise_var
        arys, shape, size = _generate_test_arrays(2, 'uint8')
        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        varval = imagedata.variance()

        expected = elementwise_var([ary.astype('float16') for ary in arys])
        assert_true(allclose(expected, varval))
        assert_equals('float16', str(varval.dtype))

    def test_stdev(self):
        from test_utils import elementwise_stdev
        arys, shape, size = _generate_test_arrays(2, 'uint8')
        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        stdval = imagedata.stdev()

        expected = elementwise_stdev([ary.astype('float16') for ary in arys])
        assert_true(allclose(expected, stdval))
        #assert_equals('float16', str(stdval.dtype))
        # it isn't clear to me why this comes out as float32 and not float16, especially
        # given that var returns float16, as expected. But I'm not too concerned about it.
        # Consider this documentation of current behavior rather than a description of
        # desired behavior.
        assert_equals('float32', str(stdval.dtype))

    def test_stats(self):
        from test_utils import elementwise_mean, elementwise_var
        arys, shape, size = _generate_test_arrays(2, 'uint8')
        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        statsval = imagedata.stats()

        floatarys = [ary.astype('float16') for ary in arys]
        # StatsCounter contains a few different measures, only test a couple:
        expectedmean = elementwise_mean(floatarys)
        expectedvar = elementwise_var(floatarys)
        assert_true(allclose(expectedmean, statsval.mean()))
        assert_true(allclose(expectedvar, statsval.variance()))

    def test_max(self):
        from numpy import maximum
        arys, shape, size = _generate_test_arrays(2, 'uint8')
        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        maxval = imagedata.max()
        assert_true(array_equal(reduce(maximum, arys), maxval))

    def test_min(self):
        from numpy import minimum
        arys, shape, size = _generate_test_arrays(2, 'uint8')
        imagedata = ImagesLoader(self.sc).fromArrays(arys)
        minval = imagedata.min()
        assert_true(array_equal(reduce(minimum, arys), minval))


class TestImagesUsingOutputDir(PySparkTestCaseWithOutputDir):

    def _run_tstSaveAsBinarySeries(self, testidx, narys_, valdtype, groupingdim_):
        """Pseudo-parameterized test fixture, allows reusing existing spark context
        """
        paramstr = "(groupingdim=%d, valuedtype='%s')" % (groupingdim_, valdtype)
        arys, aryshape, arysize = _generate_test_arrays(narys_, dtype_=valdtype)
        dims = aryshape[:]
        outdir = os.path.join(self.outputdir, "anotherdir%02d" % testidx)

        images = ImagesLoader(self.sc).fromArrays(arys)

        slicesPerDim = [1]*arys[0].ndim
        slicesPerDim[groupingdim_] = arys[0].shape[groupingdim_]
        images.toBlocks(slicesPerDim).saveAsBinarySeries(outdir)

        ndims = len(aryshape)
        # prevent padding to 4-byte boundaries: "=" specifies no alignment
        unpacker = struct.Struct('=' + 'h'*ndims + dtype(valdtype).char*narys_)

        def calcExpectedNKeys():
            tmpshape = list(dims[:])
            del tmpshape[groupingdim_]
            return prod(tmpshape)
        expectednkeys = calcExpectedNKeys()

        def byrec(f_, unpacker_, nkeys_):
            rec = True
            while rec:
                rec = f_.read(unpacker_.size)
                if rec:
                    allrecvals = unpacker_.unpack(rec)
                    yield allrecvals[:nkeys_], allrecvals[nkeys_:]

        outfilenames = glob.glob(os.path.join(outdir, "*.bin"))
        assert_equals(dims[groupingdim_], len(outfilenames))
        for outfilename in outfilenames:
            with open(outfilename, 'rb') as f:
                nkeys = 0
                for keys, vals in byrec(f, unpacker, ndims):
                    nkeys += 1
                    assert_equals(narys_, len(vals))
                    for validx, val in enumerate(vals):
                        assert_equals(arys[validx][keys], val, "Expected %g, got %g, for test %d %s" %
                                      (arys[validx][keys], val, testidx, paramstr))
                assert_equals(expectednkeys, nkeys)

        confname = os.path.join(outdir, "conf.json")
        assert_true(os.path.isfile(confname))
        with open(os.path.join(outdir, "conf.json"), 'r') as fconf:
            import json
            conf = json.load(fconf)
            assert_equals(outdir, conf['input'])
            assert_equals(tuple(dims), tuple(conf['dims']))
            assert_equals(len(aryshape), conf['nkeys'])
            assert_equals(narys_, conf['nvalues'])
            assert_equals(valdtype, conf['valuetype'])
            assert_equals('int16', conf['keytype'])

        assert_true(os.path.isfile(os.path.join(outdir, 'SUCCESS')))

    def test_saveAsBinarySeries(self):
        narys = 3
        arys, aryshape, _ = _generate_test_arrays(narys)

        outdir = os.path.join(self.outputdir, "anotherdir")
        os.mkdir(outdir)
        assert_raises(ValueError, ImagesLoader(self.sc).fromArrays(arys).toBlocks((1, 1, 1))
                      .saveAsBinarySeries, outdir)

        groupingdims = xrange(len(aryshape))
        dtypes = ('int16', 'int32', 'float32')
        paramiters = itertools.product(groupingdims, dtypes)

        for idx, params in enumerate(paramiters):
            gd, dt = params
            self._run_tstSaveAsBinarySeries(idx, narys, dt, gd)

    def _run_tst_roundtripConvertToSeries(self, images, strategy):
        outdir = os.path.join(self.outputdir, "fish-series-dir")

        partitionedimages = images.toBlocks(strategy)
        series = partitionedimages.toSeries()
        series_ary = series.pack()

        partitionedimages.saveAsBinarySeries(outdir)
        converted_series = SeriesLoader(self.sc).fromBinary(outdir)
        converted_series_ary = converted_series.pack()

        assert_equals(images.dims.count, series.dims.count)
        expected_shape = tuple([images.nimages] + list(images.dims.count))
        assert_equals(expected_shape, series_ary.shape)
        assert_true(array_equal(series_ary, converted_series_ary))

    def test_roundtripConvertToSeries(self):
        imagepath = findSourceTreeDir("utils/data/fish/tif-stack")

        images = ImagesLoader(self.sc).fromMultipageTif(imagepath)
        strategy = SimpleBlockingStrategy.generateFromBlockSize(images, blockSize=76 * 20)
        self._run_tst_roundtripConvertToSeries(images, strategy)

    def test_fromStackToSeriesWithPack(self):
        ary = arange(8, dtype=dtype('int16')).reshape((2, 4))
        filename = os.path.join(self.outputdir, "test.stack")
        ary.tofile(filename)

        image = ImagesLoader(self.sc).fromStack(filename, dims=(4, 2))
        strategy = SimpleBlockingStrategy.generateFromBlockSize(image, "150M")
        series = image.toBlocks(strategy).toSeries()

        seriesvals = series.collect()
        seriesary = series.pack()

        # check ordering of keys
        assert_equals((0, 0), seriesvals[0][0])  # first key
        assert_equals((1, 0), seriesvals[1][0])  # second key
        assert_equals((2, 0), seriesvals[2][0])
        assert_equals((3, 0), seriesvals[3][0])
        assert_equals((0, 1), seriesvals[4][0])
        assert_equals((1, 1), seriesvals[5][0])
        assert_equals((2, 1), seriesvals[6][0])
        assert_equals((3, 1), seriesvals[7][0])

        # check dimensions tuple is reversed from numpy shape
        assert_equals(ary.shape[::-1], series.dims.count)

        # check that values are in original order
        collectedvals = array([kv[1] for kv in seriesvals], dtype=dtype('int16')).ravel()
        assert_true(array_equal(ary.ravel(), collectedvals))

        # check that packing returns transpose of original array
        assert_true(array_equal(ary.T, seriesary))


if __name__ == "__main__":
    if not _have_image:
        print "NOTE: Skipping PIL/pillow tests as neither seem to be installed and functional"
    unittest.main()
    if not _have_image:
        print "NOTE: PIL/pillow tests were skipped as neither seem to be installed and functional"
