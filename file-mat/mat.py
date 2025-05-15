# File-MAT GIMP plugin
# Copyright (c) 2019-2025 Crt Vavros

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import gi
import os

gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
from gi.repository import GObject
from gi.repository import Gio
from gi.repository import Gegl

from utils import *

from array import array
from collections import namedtuple
from struct import *
from typing import List, BinaryIO


MAT_FILE_MAGIC       = b'MAT ' # mind the space at the end
MAT_REQUIRED_VERSION = 0x32
MAT_REQUIRED_TYPE    = 2

class MAT:
    """
    Class for loading and saving image to MAT file format
    for Indiana Jones and the Infernal Machine game.
    """

    def load_from_filepath(self, file_path: str, max_cells: int = -1, load_mipmap_lod_chain:bool = False) -> Gimp.Image:
        '''
        Loads MAT from file and returns image.
        :param file_path: path to the MAT file
        :param max_cells: max number of celluloid textures to load.
                          Default -1, meaning all.
        :param load_mipmap_lod_chain: Loads MipMap texture LOD images as layers. If false no LOD image is loaded.
        '''
        Gimp.progress_init(f'Loading MAT image')
        with open(file_path, 'rb') as f:
            # Read MAT header and records
            h = self._read_header(f)
            r = self._read_records(f, h)

            max_cells = h.cel_count if max_cells < 0 else min(max_cells, h.cel_count)
            Gimp.progress_update(0 / float(max_cells))

            # Create a new image
            img = Gimp.Image.new(1, 1, Gimp.ImageBaseType.RGB)
            img.set_file(Gio.file_new_for_path(os.path.splitext(file_path)[0]))

            # Read cel textures and add them to the image as layers
            for cel_idx in range(0, max_cells):
                # Read Mipmap texture chain
                Gimp.progress_update(cel_idx / float(max_cells))
                mm = self._read_texture(f, h.color_info)

                # Add Mipmap textures as layers
                for lod_num, pixdata in enumerate(mm.pixel_data_array):
                    lwidth  = mm.width >> lod_num
                    lheight = mm.height >> lod_num

                    l = MAT._add_layer(img, pixdata, lwidth, lheight, mm.color_info)
                    l.set_name(self._get_layer_name(cel_idx, lod_num))
                    if cel_idx > 0:
                        l.set_visible(False)

                    if lod_num == 0 and len(mm.pixel_data_array) > 1:
                        set_layer_as_mipmap(l, True)

                    # Skip loading LOD images?
                    if not load_mipmap_lod_chain:
                        break

            # Set image size and sanitize it
            img.resize_to_layers()
            sanitize_image(img)
            return img

    def save_to_filepath(self, file_path: str, img: Gimp.Image, cf, lod_min_size: int = 8, lod_max_levels: int = 4):
        '''
        Save MAT to file.
        :param file_path: file path where to save MAT
        :param img: The image to save in MAT file format
        :param cf: The color format to encode texture bitmap
        :param lod_min_size: minimum MipMap LOD image size
        :param lod_max_levels: maximum number of MipMap levels
        '''
        if os.path.exists(file_path):
            os.remove(file_path)

        with open(file_path, 'wb') as f:
            layers = img.get_layers()
            cel_count = len(layers)

            # Show progress
            Gimp.progress_init(f'Exporting {cel_count} image {"layer" if cel_count == 1 else "layers"} to MAT')

            self._write_header(f, cel_count, cf)
            self._write_records(f, cel_count)

            for idx, l in enumerate(reversed(layers)):
                self.write_texture(f, l, cf, lod_min_size, lod_max_levels)
                Gimp.progress_update(idx / float(cel_count))

    INDEXED, RGB, RGBA, = range(3)

    color_format = namedtuple('color_format', [
        'color_mode',
        'bpp',
        'red_bpp', 'green_bpp', 'blue_bpp',
        'red_shl', 'green_shl', 'blue_shl',
        'red_shr', 'green_shr', 'blue_shr',
        'alpha_bpp', 'alpha_shl', 'alpha_shr'
    ])
    cf_serf = Struct('<14I')

    mat_header = namedtuple('mat_header', [
        'magic',
        'version',
        'type',
        'record_count',
        'cel_count',
        'color_info'
    ])
    mh_serf = Struct('<4siIii')

    mat_record_header = namedtuple('mat_record_header', [
        'record_type',
        'transparent_color',
        'unknown_1',
        'unknown_2',
        'unknown_3',
        'unknown_4',
        'unknown_5',
        'unknown_6',
        'unknown_7',
        'cel_idx'
    ])
    mrh_serf = Struct('<10i')

    mat_mipmap_header = namedtuple('mat_mipmap_header', [
        'width',
        'height',
        'transparent',
        'unknown_1',
        'unknown_2',
        'mipmap_levels',
    ])
    mmm_serf = Struct('<6i')

    mipmap = namedtuple('mipmap', [
        'width',
        'height',
        'color_info',
        'pixel_data_array'
    ])

    @staticmethod
    def _read_header(f):
        rh = bytearray(f.read(MAT.mh_serf.size))
        rcf = bytearray(f.read(MAT.cf_serf.size))

        deser_mh = MAT.mh_serf.unpack(rh)
        cf = MAT.color_format._make(MAT.cf_serf.unpack(rcf))

        h = MAT.mat_header(deser_mh[0], deser_mh[1], deser_mh[2], deser_mh[3], deser_mh[4], cf)
        if h.magic != MAT_FILE_MAGIC:
            raise ImportError('Invalid MAT file')
        if h.version != MAT_REQUIRED_VERSION:
            raise ImportError('Invalid MAT file version')
        if h.type != MAT_REQUIRED_TYPE:
            raise ImportError('Invalid MAT file type')
        if h.record_count != h.cel_count:
            raise ImportError('Cannot read older version of MAT file')
        if h.record_count <= 0:
            raise ImportError('MAT file record count <= 0')
        if not (MAT.INDEXED < h.color_info.color_mode <= MAT.RGBA):  # must not be indexed color mode (0)
            raise ImportError('Invalid color mode')
        if h.color_info.bpp % 8 != 0 and not (16 <= h.color_info.bpp <= 32):
            raise ImportError('Invalid color depth')
        return h

    @staticmethod
    def _write_header(f, cel_count, cf):
        h = MAT.mat_header(MAT_FILE_MAGIC, MAT_REQUIRED_VERSION, MAT_REQUIRED_TYPE, cel_count, cel_count, cf)

        rh = MAT.mh_serf.pack(*h[0:5])  # not including 'color_info' field
        rcf = MAT.cf_serf.pack(*cf)
        f.write(rh)
        f.write(rcf)

    @staticmethod
    def _read_records(f, h):
        rh_list = []
        for i in range(0, h.record_count):
            mrh = MAT.mrh_serf.unpack(bytearray(f.read(MAT.mrh_serf.size)))
            rh_list.append(MAT.mat_record_header._make(mrh))
        return rh_list

    @staticmethod
    def _write_records(f, record_count):
        record_type = 8
        for i in range(0, record_count):
            r = MAT.mat_record_header(record_type, 0, 0, 0, 0, 0, 0, 0, 0, i)
            f.write(MAT.mrh_serf.pack(*r))

    @staticmethod
    def _get_img_row_len(width, bpp):
        return int(abs(width) * (bpp / 8))

    @staticmethod
    def _get_pixel_data_size(width, height, bpp):
        return int(abs(width * height) * (bpp / 8))

    @staticmethod
    def _get_encoded_pixel_size(bpp):
        return int(bpp / 8)

    @staticmethod
    def _get_decoded_pixel_size(ci):
        return 4 if ci.alpha_bpp != 0 else 3

    @staticmethod
    def _get_color_mask(bpc):
        return 0xFFFFFFFF >> (32 - bpc)
    
    @staticmethod
    def _scale_color_component(cc, src_bpp, delta_bpp):
        """Scale a color component from src_bpp to dest_bpp (where delta_bpp = src_bpp - dest_bpp)"""
        if delta_bpp <= 0:  # Upscale
            # Calculate bit pattern to fill in lower bits for better upscaling
            d_src_bpp = src_bpp + delta_bpp
            main_shift = cc << -delta_bpp
            
            if d_src_bpp >= 0:
                # Take the highest bits from source and use them for the lower bits
                fill_pattern = cc >> d_src_bpp
            else:
                # For very large bit depth increases, replicate the pattern
                fill_pattern = cc * ((1 << -delta_bpp) - 1)
                
            return main_shift | fill_pattern
        else:  # Downscale
            return cc >> delta_bpp
    
    @staticmethod
    def _decode_pixel(p, ci, rmask, gmask, bmask, amask):  # p: int, ci: color_format
        r = ((p >> ci.red_shl) & rmask)
        g = ((p >> ci.green_shl) & gmask)
        b = ((p >> ci.blue_shl) & bmask)
        
        # Set pixel tuple
        # Note, 8 is bpp for decoded pixel
        dp = (
            MAT._scale_color_component(r, ci.red_bpp  , ci.red_bpp - 8),
            MAT._scale_color_component(g, ci.green_bpp, ci.green_bpp - 8),
            MAT._scale_color_component(b, ci.blue_bpp , ci.blue_bpp - 8)
        )
        
        if ci.alpha_bpp != 0:
            a = ((p >> ci.alpha_shl) & amask)
            a = MAT._scale_color_component(a, ci.alpha_bpp, ci.alpha_bpp - 8)
            dp = dp + (a,)

        return array('B', dp)

    @staticmethod
    def _encode_pixel(p, ci):  # p: array, ci: color_format
        r = p[0]
        g = p[1]
        b = p[2]

        e_p = ((r >> ci.red_shr) << ci.red_shl) | \
              ((g >> ci.green_shr) << ci.green_shl) | \
              ((b >> ci.blue_shr) << ci.blue_shl)

        if ci.alpha_bpp != 0:
            a    = p[3] if len(p) == 4 else 255
            e_p |= ((a >> ci.alpha_shr) << ci.alpha_shl)

        return int(e_p)

    @staticmethod
    def _decode_pixel_data(pd, width, height, ci) -> array:  # ci: color_format
        e_pixel_size = MAT._get_encoded_pixel_size(ci.bpp)
        e_row_len    = MAT._get_img_row_len(width, ci.bpp)
        d_pixel_size = MAT._get_decoded_pixel_size(ci)
        d_row_len    = d_pixel_size * width
        dpd          = array('B', bytes(height * d_row_len))

        rmask = MAT._get_color_mask(ci.red_bpp)
        gmask = MAT._get_color_mask(ci.green_bpp)
        bmask = MAT._get_color_mask(ci.blue_bpp)
        amask = MAT._get_color_mask(ci.alpha_bpp)

        for r in range(0, height):
            e_row_idx = r * e_row_len
            d_row_idx = r * d_row_len
            for c in range(0, e_row_len, e_pixel_size):
                # decode pixel as little endian integer
                pixel = 0
                i = c + e_row_idx
                for b in reversed(pd[i: i + e_pixel_size]):
                    pixel = pixel << 8 | b

                d_pos = (c // e_pixel_size) * d_pixel_size + d_row_idx
                dpd[d_pos: (d_pos + d_pixel_size)] = MAT._decode_pixel(pixel, ci, rmask, gmask, bmask, amask)
        return dpd

    @staticmethod
    def _encode_pixel_buffer(buffer: Gegl.Buffer, ci) -> array:  # pr: Gegl.Buffer ci: color_format
        width        = buffer.props.width
        height       = buffer.props.height
        bpp          = buffer.props.px_size
        row_len      = width * bpp
        e_pixel_size = MAT._get_encoded_pixel_size(ci.bpp)
        e_row_len    = e_pixel_size * width
        epd          = array('B', bytes(height * e_row_len))

        # encode pixel as little endian
        fmt = 'B' if e_pixel_size == 1 else '<H' if e_pixel_size == 2 else '<I'

        rect     = Gegl.Rectangle.new(0, 0, width, height)
        img_data = buffer.get(rect, 1.0, None, Gegl.AbyssPolicy.NONE)
        pixels   = tuple(array('B', img_data))
        
        for y in range(0, height):
            row_idx = y * row_len
            for x in range(0, width):
                p_ofs = x * bpp + row_idx
                p     = pixels[p_ofs: p_ofs + bpp]  # get pixel. bpp is bytes per pixel
                
                e_p = MAT._encode_pixel(p, ci)
                e_p = array('B', pack(fmt, e_p))
                if e_pixel_size == 3:
                    e_p = e_p[:3]

                e_pos = x * e_pixel_size + y * e_row_len
                epd[e_pos: (e_pos + e_pixel_size)] = e_p
        return epd

    @staticmethod
    def _read_pixel_data(f: BinaryIO, width: int, height: int, ci):  # f: file ci: color_format
        pd_size = MAT._get_pixel_data_size(width, height, ci.bpp)
        pd = bytearray(f.read(pd_size))
        return MAT._decode_pixel_data(pd, width, height, ci)

    @staticmethod
    def _write_pixel_data(f: BinaryIO, pixels: Gegl.Buffer, ci):  # f: file  ci: color_format
        epd = MAT._encode_pixel_buffer(pixels, ci)
        f.write(epd)

    @staticmethod
    def _read_texture(f, ci):  # f: file ci: color_format
        mmh_raw = MAT.mmm_serf.unpack(bytearray(f.read(MAT.mmm_serf.size)))
        mmh = MAT.mat_mipmap_header._make(mmh_raw)

        pd = []
        for i in range(0, mmh.mipmap_levels):
            w = mmh.width  >> i
            h = mmh.height >> i
            pd += [MAT._read_pixel_data(f, w, h, ci)]
        return MAT.mipmap(mmh.width, mmh.height, ci, pd)

    @staticmethod
    def write_texture(f, layer: Gimp.Layer, ci, min_mipmap_size, max_mipmap_levels):  # f:file, layer:Gimp.Layer, ci:color_format, min_mipmap_size:int, max_mipmap_levels:int
        # Get the buffer from the layer
        pixels = layer.get_buffer()

        lod_pixels = [pixels]
        if is_layer_mipmap(layer):
            lod_pixels += make_mipmap_lods(layer, min_mipmap_size, max_mipmap_levels -1 if max_mipmap_levels >= 0 else -1)

        mmh = MAT.mat_mipmap_header(layer.get_width(), layer.get_height(), 0, 0, 0, len(lod_pixels))
        f.write(MAT.mmm_serf.pack(*mmh))

        for idx, pixels in enumerate(lod_pixels):
            print(f'Writing lod={idx}')
            MAT._write_pixel_data(f, pixels, ci)

    @staticmethod
    def _get_layer_name(cel_idx, lod_num):
        name = 'cel_' + str(cel_idx)
        if lod_num > 0:
            name += '_lod_' + str(lod_num)
        return name

    @staticmethod
    def _add_layer(img, pixdata, width, height, ci):
        # Create a new layer with the appropriate type
        #
        # Format reference: https://gegl.org/babl/Reference.html
        # Note format must be RGB with perceptual (sRGB) TRC  otherwise the gamma will be applied
        # to the images and the image will be too bright.
        if ci.alpha_bpp != 0:
            format = "R~G~B~A u8"
            layer_type = Gimp.ImageType.RGBA_IMAGE
        else:
            format = "R~G~B~ u8"
            layer_type = Gimp.ImageType.RGB_IMAGE

        layer = Gimp.Layer.new(img, "", width, height, layer_type, 100.0, Gimp.LayerMode.NORMAL)
        
        # Write pixels to layer
        rect = Gegl.Rectangle.new(0, 0, width, height)
        buffer = layer.get_buffer()
        buffer.set(rect, format, pixdata)
        
        # Add the layer to the image
        img.insert_layer(layer, None, -1)  # None for parent, -1 for position (top)
        
        return layer
