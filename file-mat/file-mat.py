#!/usr/bin/env python3

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

# GIMP Plug-in for MAT file format of the game Indiana Jones and the Infernal Machine

import gi
gi.require_version('Gimp', '3.0')
gi.require_version('GimpUi', '3.0')
from gi.repository import Gimp, GimpUi, GObject, Gio, GLib, Gtk, GdkPixbuf

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import *
from mat import *

import gettext
_ = gettext.gettext

AUTHOR           = 'Crt Vavros'
COPYRIGHT        = AUTHOR
COPYRIGHT_YEAR   = '2025'

# Procedure registration information
PROC_NAME        = 'file-ijim-mat'
EDITOR_PROC      = f'{PROC_NAME}-export-dialog'
EXPORT_PROC      = f'{PROC_NAME}-export'
LOAD_PROC        = f'{PROC_NAME}-load'
LOAD_THUMB_PROC  = f'{PROC_NAME}-load-thumb'

DEBUG_MODE             = False
LOAD_MIPMAP_LOD_CHAIN  = False # If True all images from Mipmap LOD chain will be displayed

DEFAULT_MAX_MIPMAP_LEVEL  = 4
DEFAULT_MIN_MIPMAP_SIZE   = 16
INPUT_MAX_MIPMAP_LEVEL    = 16
INPUT_MAX_MIN_MIPMAP_SIZE = 128
THUMBNAIL_SIZE            = 128

script_path = os.path.abspath(__file__)
script_dir  = os.path.dirname(script_path)

if DEBUG_MODE:
    log_path       = f'{script_dir}/file-mat.log'
    error_log_path = f'{script_dir}/file-mat-error.log'

    if os.path.exists(log_path):
        os.remove(log_path)
    if os.path.exists(error_log_path):
        os.remove(error_log_path)
    sys.stdout = open(log_path, "w")
    sys.stderr = open(error_log_path, "w")

def thumbnail_mat(procedure, file, thumb_size, args, data):
    try:
        mat = MAT()
        img = mat.load_from_filepath(file.peek_path(), max_cells=1)

        # Scale image
        img    = img.duplicate()
        width  = img.get_width()
        height = img.get_height()
        scale  = float(thumb_size) / max(width, height)
        if scale and scale != 1.0:
            swidth  = int(width * scale)
            sheight = int(height * scale)
            img.scale(swidth, sheight)

        return Gimp.ValueArray.new_from_values([
            GObject.Value(Gimp.PDBStatusType, Gimp.PDBStatusType.SUCCESS),
            GObject.Value(Gimp.Image, img),
            GObject.Value(GObject.TYPE_INT, width),
            GObject.Value(GObject.TYPE_INT, height),
            GObject.Value(GObject.TYPE_INT, len(img.get_layers()))
        ])
    except Exception as e:
        error = GLib.Error()
        error.message = f'Error loading MAT file:\n\n{str(e)}!'
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, error)

def load_mat(procedure, run_mode, file, metadata, flags, config, *run_data):
    try:
        mat = MAT()
        img = mat.load_from_filepath(file.peek_path(), load_mipmap_lod_chain=LOAD_MIPMAP_LOD_CHAIN)
        if len(img. get_layers()) == 0:
            raise ImportError('No textures to load')

        return Gimp.ValueArray.new_from_values([
            GObject.Value(Gimp.PDBStatusType, Gimp.PDBStatusType.SUCCESS),
            GObject.Value(Gimp.Image, img),
        ]), flags

    except Exception as e:
        error = GLib.Error()
        error.message = f'Error loading MAT file:\n\n{str(e)}!'
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, error)
               
def export_mat(procedure, run_mode, image, file, options, metadata, config, data):
    GimpUi.init(EXPORT_PROC)
    
    class ExportDialog(GimpUi.Dialog):
        COL_IDX_LAYER      = 0
        COL_IDX_THUMB      = 1
        COL_IDX_INFO       = 2
        COL_IDX_IS_MIPMAP  = 3 
        COL_IDX_EXPORT     = 4
        COL_IDX_CEL_NUM    = 5
        RESPONSE_EXPORT    = 1

        def __init__(self):
            GimpUi.Dialog.__init__(self, 
               title=_('Export Image as MAT'), role=EDITOR_PROC,
               parent=None, modal=True
            )
            
            self.eimg = image.duplicate()
            
            self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
            self.add_button(_("Export"), self.RESPONSE_EXPORT)

            self.set_name(EDITOR_PROC)
            self.connect('response', self.on_response)
            self.connect('destroy', self.on_destroy)

            self.lod_max_levels = DEFAULT_MAX_MIPMAP_LEVEL
            self.lod_min_size   = DEFAULT_MIN_MIPMAP_SIZE

            export_opt_box      = self.make_export_options_box()
            self.img_view_frame = self.make_image_view()

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            hbox.pack_start(export_opt_box, True, True, 40)
            hbox.pack_start(self.img_view_frame, True, True, 15)

            self.get_content_area().pack_start(hbox, True, True, 0)
            self.show_all()

            self.set_resizable(False)

        def __del__(self):
            Gimp.Image.delete(self.eimg)

        def make_export_options_box(self):
            # Color depth
            self.rb_color_16bit      = Gtk.RadioButton(label='16 bit')
            self.cb_16bit_alpha_1bit = Gtk.CheckButton(label='Alpha 1 bit')
            self.cb_16bit_alpha_1bit.set_tooltip_text(_('Export in RGBA-5551 format when image has alpha channel.'))
            self.rb_color_32bit      = Gtk.RadioButton.new_from_widget(self.rb_color_16bit)
            self.rb_color_32bit.set_label('32 bit')

            # Enable/Disable 1 bit alpha checkbox whene color depth radio button is clicked
            self.rb_color_16bit.connect('toggled', lambda b: self.cb_16bit_alpha_1bit.set_sensitive(True))
            self.rb_color_32bit.connect('toggled', lambda b: self.cb_16bit_alpha_1bit.set_sensitive(False))

            # Place color depth radio buttons in a box
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            box.pack_start(self.rb_color_16bit, False, False, 0)

            # 1 bit alpha checkbox
            a1bit_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            a1bit_hbox.pack_start(self.cb_16bit_alpha_1bit, False, False, 20)
            box.pack_start(a1bit_hbox, False, False, 0)

            # 32 bit radio button
            box.pack_start(self.rb_color_32bit, False, False, 0)

            # Add box to a frame
            cdo_frame = Gtk.Frame(label='Color Depth:')
            cdo_frame.add(box)

            # Min MM size
            adjustment = Gtk.Adjustment(value=self.lod_min_size, 
                                        lower=2, 
                                        upper=INPUT_MAX_MIN_MIPMAP_SIZE, 
                                        step_increment=1)
            sb_mm_min_size = Gtk.SpinButton(adjustment=adjustment)
            sb_mm_min_size.set_tooltip_text(_('Min size of Mipmap LOD texture'))
            sb_mm_min_size.set_numeric(True)
            sb_mm_min_size.set_update_policy(Gtk.SpinButtonUpdatePolicy.IF_VALID)

            def sb_mm_min_size_changed(sp):
                val = sp.get_value_as_int()
                if val != self.lod_min_size:
                    if val > self.lod_min_size:
                        self.lod_min_size = self.lod_min_size << 1
                    else:
                        self.lod_min_size = self.lod_min_size >> 1
                    sp.set_value(self.lod_min_size)
            sb_mm_min_size.connect('changed', sb_mm_min_size_changed)

            t_mm_min_size = Gtk.Grid()
            t_mm_min_size.attach(Gtk.Label(label='Min Size:  '), 0, 0, 1, 1)
            t_mm_min_size.attach(sb_mm_min_size, 1, 0, 1, 1)

            # Max MM level
            adjustment = Gtk.Adjustment(value=self.lod_max_levels, 
                                    lower=1, 
                                    upper=INPUT_MAX_MIPMAP_LEVEL, 
                                    step_increment=1)
            sb_mm_level_count = Gtk.SpinButton(adjustment=adjustment)
            sb_mm_level_count.set_tooltip_text(_('Max Mipmap LOD level'))
            sb_mm_level_count.set_numeric(True)
            sb_mm_level_count.set_update_policy(Gtk.SpinButtonUpdatePolicy.IF_VALID)

            def sb_mm_max_level_changed(sp):
                self.lod_max_levels = sp.get_value_as_int()
            sb_mm_level_count.connect('changed', sb_mm_max_level_changed)

            t_mm_level_count = Gtk.Grid()
            t_mm_level_count.attach(Gtk.Label(label='Max Level:  '), 0, 0, 1, 1)
            t_mm_level_count.attach(sb_mm_level_count, 1, 0, 1, 1)

            # Toggle Mipmap button
            btnToggleMipMap = Gtk.Button(label='Toggle Mipmap')
            btnToggleMipMap.set_tooltip_text(_('Toggle On/Off Mipmap exporting for all textures'))
            
            def btn_toggle_mipmap(btn):
                # Store our state in a custom property
                mip_on = getattr(btn, 'mipmap_toggle_state', False)
                mip_on = not mip_on
                setattr(btn, 'mipmap_toggle_state', mip_on)
                for row in self.liststore:
                    row[self.COL_IDX_IS_MIPMAP] = bool(mip_on)
            btnToggleMipMap.connect('clicked', btn_toggle_mipmap)

            # Mipmap option frame
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_homogeneous(True)
            box.pack_start(t_mm_min_size, False, False, 0)
            box.pack_start(t_mm_level_count, False, False, 0)
            box.pack_start(btnToggleMipMap, False, False, 0)
            mmo_frame = Gtk.Frame(label='Mipmap Options:')
            mmo_frame.add(box)

            # Main option frame
            o_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            o_box.pack_start(cdo_frame, False, False, 10)
            o_box.pack_start(mmo_frame, False, False, 10)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.set_size_request(145, -1)
            box.pack_start(o_box, True, False, 0)

            return box

        def make_image_view(self):
            # Create a ListStore model
            self.liststore = Gtk.ListStore(GObject.TYPE_PYOBJECT, GdkPixbuf.Pixbuf, str, bool, bool, int) # layer, thumbnail image, info text, is_mipmap, export, cel_num
            
            for idx, layer in enumerate(reversed(self.eimg.get_layers())):
                pbuf = self.get_layer_thumbnail(layer)
                img_info = '<b>Name</b>: {}'.format(layer.get_name())
                img_info += '\n<b>Size</b>: {}x{}'.format(layer.get_width(), layer.get_height())
                img_info += '\n<b>Color</b>: {}'.format('RGB' if self.eimg.get_base_type() == Gimp.ImageBaseType.RGB else 'Grayscale' if self.eimg.get_base_type() == Gimp.ImageBaseType.GRAY else 'Indexed')
                self.liststore.append([layer, pbuf, img_info, is_layer_mipmap(layer), True, idx])

            self.export_tex_count = len(self.liststore)

            self.treeview = Gtk.TreeView(model=self.liststore)
            self.treeview.set_enable_search(False)
            self.treeview.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
            self.treeview.get_selection().set_mode(Gtk.SelectionMode.NONE)

            # Column 'Cel num'
            renderer = Gtk.CellRendererText()
            col_cel_num = Gtk.TreeViewColumn('Cel No.', renderer, text=self.COL_IDX_CEL_NUM)
            col_cel_num.pack_start(renderer, False)
            
            col_cel_num_header = Gtk.Label(label='Cel No.')
            col_cel_num_header.show_all()

            tooltip = Gtk.Tooltip()
            col_cel_num_header.set_tooltip_text('MAT CEL number.\ni.e.: The sequence number of layer texture when exported to MAT file.')

            col_cel_num.set_widget(col_cel_num_header)
            self.treeview.append_column(col_cel_num)

            # Column 'Texture'
            pixrd = Gtk.CellRendererPixbuf()
            col_pixbuf = Gtk.TreeViewColumn('Texture', pixrd, pixbuf=self.COL_IDX_THUMB)
            col_pixbuf.set_min_width(THUMBNAIL_SIZE)
            self.treeview.append_column(col_pixbuf)

            # Column 'Info'
            col_info = Gtk.TreeViewColumn()

            # column tooltip
            col_info_header = Gtk.Label(label='Info & Options')
            col_info_header.show_all()
            col_info.set_widget(col_info_header)

            col_info_header.set_tooltip_text("Layer info and export options.\nIf 'Mipmap' is checked, layer image will be exported as Mipmap texture.")

            # info text
            renderer = Gtk.CellRendererText()
            renderer.set_property('width', 0)
            renderer.set_property('yalign', 0.4)
            renderer.set_property('height', THUMBNAIL_SIZE)
            col_info.pack_start(renderer, False)
            col_info.add_attribute(renderer, 'markup', self.COL_IDX_INFO)

            # label Mipmap
            renderer = Gtk.CellRendererText()
            renderer.set_property('markup', '<b>Mipmap</b>:')
            renderer.set_property('xalign', 0.0)
            renderer.set_property('yalign', 0.85)
            col_info.pack_start(renderer, False)

            # CB Mipmap
            renderer = Gtk.CellRendererToggle()
            renderer.set_property('xalign', 0.0)
            renderer.set_property('yalign', 0.85)
            renderer.set_property('width', 158)

            def on_cb_mipmap_toggled(widget, path):
                is_mipmap = not self.liststore[path][self.COL_IDX_IS_MIPMAP]
                self.liststore[path][self.COL_IDX_IS_MIPMAP] = is_mipmap
                set_layer_as_mipmap(self.liststore[path][self.COL_IDX_LAYER], is_mipmap)

            renderer.connect('toggled', on_cb_mipmap_toggled)

            col_info.pack_start(renderer, True)
            col_info.add_attribute(renderer, 'active', self.COL_IDX_IS_MIPMAP)

            self.treeview.append_column(col_info)

            # Column 'Export'
            def on_cb_export_toggled(widget, path):
                row = self.liststore[path]
                export = not row[self.COL_IDX_EXPORT]
                row[self.COL_IDX_EXPORT] = export
                self.export_tex_count += 1 if export else -1
                self.set_btn_export_sensitive(self.export_tex_count > 0)
                self.img_view_frame.set_label('Cel texture(s) to export: {}'.format(self.export_tex_count))

                # re-enumerate rows
                idx = 0
                row[self.COL_IDX_CEL_NUM] = idx if export else -1
                for row in self.liststore:
                    if row[self.COL_IDX_CEL_NUM] > -1:
                        row[self.COL_IDX_CEL_NUM] = idx
                        idx += 1

            cb_export = Gtk.CellRendererToggle()
            cb_export.connect('toggled', on_cb_export_toggled)

            col_export = Gtk.TreeViewColumn('Export', cb_export)
            col_export.add_attribute(cb_export, 'active', self.COL_IDX_EXPORT)
            
            col_export_header = Gtk.Label(label='Export')
            col_export_header.show_all()
            col_export_header.set_tooltip_text('Export texture to file.')
            col_export.set_widget(col_export_header)
            
            self.treeview.append_column(col_export)

            # Scroll window & root frame
            scrl_win = Gtk.ScrolledWindow()
            scrl_win.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrl_win.add(self.treeview)
            scrl_win.set_size_request(THUMBNAIL_SIZE, THUMBNAIL_SIZE * 4)

            frame_imgs = Gtk.Frame(label='Texture(s) to export: {}'.format(self.export_tex_count))
            frame_imgs.set_property('label-xalign', 0.05)
            frame_imgs.add(scrl_win)
            frame_imgs.set_size_request(535, -1)

            return frame_imgs

        def get_layer_thumbnail(self, layer):
            from gi.repository import GdkPixbuf
            
            width = layer.get_width()
            height = layer.get_height()
            
            print('get_layer_thumbnail: layer w={}, h={}'.format(width, height))
            
            img = Gimp.Image.new(width, height, Gimp.ImageBaseType.RGB)
            lcpy = Gimp.Layer.new_from_drawable(layer, img)
            lcpy.set_visible(True)
            img.insert_layer(lcpy, None, 0)
            
            scale = float(THUMBNAIL_SIZE) / max(width, height)
            if scale and scale != 1.0:
                width = int(width * scale)
                height = int(height * scale)
            
            buffer = Gimp.Image.get_thumbnail(img, width, height, Gimp.PixbufTransparency.SMALL_CHECKS)

            Gimp.Image.delete(img)
            print('get_layer_thumbnail: thumbnail width={} height={}'.format(buffer.get_width(), buffer.get_height()))
            return buffer

        def has_alpha(self, img):
            for layer in img.get_layers():
                if layer.has_alpha():
                    return True
            return False

        def get_export_color_format(self):
            alpha = self.has_alpha(self.eimg)
            if self.rb_color_16bit.get_active():
                if alpha:
                    if self.cb_16bit_alpha_1bit.get_active():
                        return MAT.color_format(MAT.RGBA, 16, 5,5,5, 11,6,1, 3,3,3, 1,0,7) #RGBA5551
                    return MAT.color_format(MAT.RGBA, 16, 4,4,4, 12,8,4, 4,4,4, 4,0,4) #RGBA4444
                return MAT.color_format(MAT.RGB, 16, 5,6,5, 11,5,0, 3,2,3, 0,0,0) #RGB565
            else: # 32 bit
                if alpha:
                    return MAT.color_format(MAT.RGBA, 32, 8,8,8, 24,16,8, 0,0,0, 8,0,0) #RGBA8888
                return MAT.color_format(MAT.RGB, 24, 8,8,8, 16,8,0, 0,0,0, 0,0,0) #RGB888

        def export_image(self):
            mat = MAT()
            if self.eimg.get_base_type() != Gimp.ImageBaseType.RGB:
                Gimp.Image.convert_rgb(self.eimg)

            for row in self.liststore:
                if not row[self.COL_IDX_EXPORT]: # 4 - include in export
                    self.eimg.remove_layer(row[self.COL_IDX_LAYER])

            # Export image as MAT file format
            cf = self.get_export_color_format()
            mat.save_to_filepath(file.peek_path(), self.eimg, cf, self.lod_min_size, self.lod_max_levels)

        def set_btn_export_sensitive(self, sensitive):
            self.get_widget_for_response(self.RESPONSE_EXPORT).set_sensitive(sensitive)

        def on_response(self, dialog, response_id):
            self.destroy()
            
            if response_id == self.RESPONSE_EXPORT:
                self.export_image()
                Gtk.main_quit()
            else:
                Gtk.main_quit()

        def on_destroy(self, widget):
            Gtk.main_quit()

    ExportDialog()
    Gtk.main()
    
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


class FileMat(Gimp.PlugIn):
    def do_query_procedures(self):
        return [EXPORT_PROC, LOAD_PROC, LOAD_THUMB_PROC]

    def do_create_procedure(self, name):
        if name == LOAD_PROC:
            procedure = Gimp.LoadProcedure.new(self, name,
                                               Gimp.PDBProcType.PLUGIN,
                                               load_mat, None)
            procedure.set_menu_label(_("Indiana Jones and the Infernal Machine"))
            procedure.set_documentation(
                _('Loads texture file format (.mat) of the game Indiana Jones and the Infernal Machine'),
                _('Loads texture file format (.mat) of the game Indiana Jones and the Infernal Machine'),
                name)
            procedure.set_attribution(AUTHOR, COPYRIGHT, COPYRIGHT_YEAR)
            procedure.set_extensions("mat")
            procedure.set_mime_types("image/mat")
            procedure.set_magics("0,string," + str(MAT_FILE_MAGIC) + chr(MAT_REQUIRED_VERSION))
            procedure.set_thumbnail_loader(LOAD_THUMB_PROC)

            return procedure
        elif name == LOAD_THUMB_PROC:
            procedure = Gimp.ThumbnailProcedure.new(self, name,
                                                    Gimp.PDBProcType.PLUGIN,
                                                    thumbnail_mat, None)
            procedure.set_documentation(
                _('Loads a thumbnail preview texture file format (.mat) of the game Indiana Jones and the Infernal Machine'),
                _('Loads a thumbnail preview texture file format (.mat) of the game Indiana Jones and the Infernal Machine'),
                name)
            procedure.set_attribution(AUTHOR, COPYRIGHT, COPYRIGHT_YEAR)

            return procedure
        elif name == EXPORT_PROC:
            procedure = Gimp.ExportProcedure.new(self, name,
                                                 Gimp.PDBProcType.PLUGIN,
                                                 False, export_mat, None)
            procedure.set_image_types("RGB\*")
            procedure.set_menu_label(_("Indiana Jones and the Infernal Machine material"))
            procedure.set_documentation(
                _('Saves images in texture file format (.mat) of the game Indiana Jones and the Infernal Machine'),
                _('Saves images in texture file format (.mat) of the game Indiana Jones and the Infernal Machine'),
                name)
            procedure.set_attribution(AUTHOR, COPYRIGHT, COPYRIGHT_YEAR)
            procedure.set_extensions("mat")
            
            return procedure

        return None

Gimp.main(FileMat.__gtype__, sys.argv)
