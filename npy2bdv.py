# Fast writing of numpy arrays to HDF5 format compatible with Fiji/BigDataViewer and BigStitcher
# Inspired by https://github.com/tlambert03/imarispy and Adam Glaser code
# Author: Nikita Vladimirov
# MIT license
import os
import h5py
import numpy as np
from xml.etree import ElementTree as ET
import skimage.transform


class BdvWriter:
    def __init__(self, filename, nsetups=1, subsamp=((1, 1, 1),), compression=None):
        """Class for writing multiple numpy 3d-arrays into BigDataViewer/BigStitcher HDF5 file.

        Parameters:
            filename: (string) full path to a new file
            nsetups: (int) total number of setups (e.g. angles or channels)
            subsamp: (tuple of tuples) subsampling levels in z,y,x order. Integers >= 1, default value ((1, 1, 1),)
            compression: (None, 'gzip', 'lzf'), HDF5 compression method. Default is None, for high-speed writing.

        Notes: input stacks and output files are assumed uint16 type.

        Example: 2 time points, 2 channels.
            fname = "./fish_timeser40_chan2_classtest6.h5"
            bdv_writer = BdvWriter(fname, nsetups = 2, subsamp=((1,1,1),))
            bdv_writer.write_setups_header()
            stack = np.random.randint(0,100,size=(41,1024,2048),dtype='int16')
            bdv_writer.append_view(stack,itime=0,isetup=0)
            bdv_writer.append_view(stack,itime=0,isetup=1)
            bdv_writer.append_view(stack,itime=1,isetup=0)
            bdv_writer.append_view(stack,itime=1,isetup=1)
            bdv_writer.write_xml_file(ntimes=2, nchannels=2)
            bdv_writer.close()
        """
        assert compression in (None, 'gzip', 'lzf'), 'Unknown compression type'
        assert not os.path.exists(filename), "File already exists, writing terminated"
        assert all([isinstance(element, int) for tupl in subsamp for element in
                    tupl]), 'subsamp values should be integers >= 1.'

        self.nsetups = nsetups
        self.subsamp = np.asarray(subsamp)
        self.chunks = self.compute_chunk_size(self.subsamp)
        self.stack_shape = None
        self.compression = compression
        self.filename = filename
        self.file_object = h5py.File(filename, 'a')

    def write_setups_header(self):
        """Write resolutions and subdivisions for all setups into h5 file."""
        for isetup in range(self.nsetups):
            grp = self.file_object.create_group('s{:02d}'.format(isetup))
            data_subsamp = np.flip(self.subsamp, 1)
            data_chunks = np.flip(self.chunks, 1)
            grp.create_dataset('resolutions', data=data_subsamp, dtype='<f8')
            grp.create_dataset('subdivisions', data=data_chunks, dtype='<i4')

    def append_view(self, stack, itime, isetup):
        """Write numpy 3-dimensional array (stack) to h5 file at specified timepint (itime) and setup number (isetup).
        Parameters:
            stack, 3d numpy array in (z,y,x) order, type 'uint16'.
            itime, integer value for time index,
            isetup, integer for setup (view, channel, or angle)
        """
        assert (0 <= isetup < self.nsetups), "Setup number out of range (nsetups=" + str(self.nsetups) + ")"
        assert len(stack.shape) == 3, "Stack should be a 3-dimensional numpy array (z,y,x)"
        self.stack_shape = stack.shape
        fmt = 't{:05d}/s{:02d}/{}'
        nlevels = len(self.subsamp)
        for ilevel in range(nlevels):
            grp = self.file_object.create_group(fmt.format(itime, isetup, ilevel))
            subdata = self.subsample_stack(stack, self.subsamp[ilevel])
            grp.create_dataset('cells', data=subdata, chunks=self.chunks[ilevel],
                               maxshape=(None, None, None), compression=self.compression)

    def compute_chunk_size(self, subsamp):
        """Compute optimal size of h5 chunks for fast reading and writing.

        Notes: For now, chunk sizes are the same for all levels. The h5 recommended chunk size should be between 10 KB and 1 MB, larger for large arrays.
        For example, chunk dimensions (4,256,256)px gives ~0.5MB chunk size for type int16 (2 bytes) and writes very fast.
        Chunk size can be larger than stack dimension.
        """
        chunks = []
        base_levels = (4, 256, 256)
        for ilevel in range(len(subsamp)):
            chunks.append(base_levels)
        chunks_tuple = tuple(chunks)
        return chunks_tuple

    def subsample_stack(self, stack, subsamp_level):
        """Subsampling of 3d stack.
        Parameters:
            stack, numpy 3d array (z,y,x) of int16
            subsamp_level, array-like with 3 elements, eg (2,4,4) for downsampling z(x2), x and y (x4).
        Return:
            down-scaled stack, unit16 type.
        """
        if all(subsamp_level[:] == 1):
            stack_sub = stack
        else:
            stack_sub = skimage.transform.downscale_local_mean(stack, tuple(subsamp_level)).astype(np.uint16)
        return stack_sub

    def write_xml_file(self, ntimes=1, nilluminations=1, nchannels=1, ntiles=1, nangles=1,
                       units='px', dx=1, dy=1, dz=1):
        """
        Write XML header file for the HDF5 file.

        Parameters:
            ntimes, int, number of time points
            nilluminations, int, num of illumination setups
            nchannels, int, num of channel setups
            ntiles, int, num of tiles
            nangles, int, num of acquisition angles
            units, string, can be anything. Default is 'px'.
            dx, dy, dz, float, pixel size in 'units'.
        """
        assert ntimes >= 1, "Total number of time points must be at least 1."
        assert nilluminations >= 1, "Total number of illuminations must be at least 1."
        assert nchannels >= 1, "Total number of channels must be at least 1."
        assert ntiles >= 1, "Total number of tiles must be at least 1."
        assert nangles >= 1, "Total number of angles must be at least 1."
        nz, ny, nx = tuple(self.stack_shape)
        root = ET.Element('SpimData')
        root.set('version', '0.2')
        bp = ET.SubElement(root, 'BasePath')
        bp.set('type', 'relative')
        bp.text = '.'

        seqdesc = ET.SubElement(root, 'SequenceDescription')
        imgload = ET.SubElement(seqdesc, 'ImageLoader')
        imgload.set('format', 'bdv.hdf5')
        el = ET.SubElement(imgload, 'hdf5')
        el.set('type', 'relative')
        el.text = os.path.basename(self.filename)
        viewsets = ET.SubElement(seqdesc, 'ViewSetups')

        # write ViewSetups
        nsetups = 0
        for iillumination in range(nilluminations):
            for ichannel in range(nchannels):
                for itile in range(ntiles):
                    for iangle in range(nangles):
                        vs = ET.SubElement(viewsets, 'ViewSetup')
                        ET.SubElement(vs, 'id').text = str(nsetups)
                        ET.SubElement(vs, 'name').text = 'setup ' + str(nsetups)
                        ET.SubElement(vs, 'size').text = '{} {} {}'.format(nx, ny, nz)
                        vox = ET.SubElement(vs, 'voxelSize')
                        ET.SubElement(vox, 'unit').text = units
                        ET.SubElement(vox, 'size').text = '{} {} {}'.format(dx, dy, dz)
                        a = ET.SubElement(vs, 'attributes')
                        ET.SubElement(a, 'illumination').text = str(iillumination)
                        ET.SubElement(a, 'channel').text = str(ichannel)
                        ET.SubElement(a, 'tile').text = str(itile)
                        ET.SubElement(a, 'angle').text = str(iangle)
                        nsetups += 1

        assert nsetups == self.nsetups, "nsetups in XML file does not match nsetups in h5 file."

        # write Attributes (range of values)
        attrs_illum = ET.SubElement(viewsets, 'Attributes')
        attrs_illum.set('name', 'illumination')
        for iilumination in range(nilluminations):
            illum = ET.SubElement(attrs_illum, 'Illumination')
            ET.SubElement(illum, 'id').text = str(iilumination)
            ET.SubElement(illum, 'name').text = 'illumination ' + str(iilumination)

        attrs_chan = ET.SubElement(viewsets, 'Attributes')
        attrs_chan.set('name', 'channel')
        for ichannel in range(nchannels):
            chan = ET.SubElement(attrs_chan, 'Channel')
            ET.SubElement(chan, 'id').text = str(ichannel)
            ET.SubElement(chan, 'name').text = 'channel ' + str(ichannel)

        attrs_tile = ET.SubElement(viewsets, 'Attributes')
        attrs_tile.set('name', 'tile')
        for itile in range(ntiles):
            tile = ET.SubElement(attrs_tile, 'Tile')
            ET.SubElement(tile, 'id').text = str(itile)
            ET.SubElement(tile, 'name').text = 'tile ' + str(itile)

        attrs_ang = ET.SubElement(viewsets, 'Attributes')
        attrs_ang.set('name', 'angle')
        for iangle in range(nangles):
            ang = ET.SubElement(attrs_ang, 'Angle')
            ET.SubElement(ang, 'id').text = str(iangle)
            ET.SubElement(ang, 'name').text = 'angle ' + str(iangle)

            # Time points
        tpoints = ET.SubElement(seqdesc, 'Timepoints')
        tpoints.set('type', 'range')
        ET.SubElement(tpoints, 'first').text = str(0)
        ET.SubElement(tpoints, 'last').text = str(ntimes - 1)

        # Transformations of coordinate system, including calibration
        vregs = ET.SubElement(root, 'ViewRegistrations')
        for itime in range(ntimes):
            for iset in range(nsetups):
                vreg = ET.SubElement(vregs, 'ViewRegistration')
                vreg.set('timepoint', str(itime))
                vreg.set('setup', str(iset))
                vt = ET.SubElement(vreg, 'ViewTransform')
                vt.set('type', 'affine')
                ET.SubElement(vt, 'Name').text = 'calibration'
                ET.SubElement(vt, 'affine').text = '{} 0.0 0.0 0.0 0.0 {} 0.0 0.0 0.0 0.0 {} 0.0'.format(dx, dy, dz)

        self.xml_indent(root)
        tree = ET.ElementTree(root)
        tree.write(os.path.splitext(self.filename)[0] + ".xml", xml_declaration=True, encoding='utf-8', method="xml")
        return

    def xml_indent(self, elem, level=0):
        """Pretty printing function"""
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                self.xml_indent(elem, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    def close(self):
        """Close the file object."""
        self.file_object.close()

