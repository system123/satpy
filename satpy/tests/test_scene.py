#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2010-2019 Satpy developers
#
# This file is part of satpy.
#
# satpy is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# satpy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# satpy.  If not, see <http://www.gnu.org/licenses/>.
"""Unit tests for scene.py."""

import math
import os
import random
import string
import unittest
from copy import deepcopy
from datetime import datetime
from unittest import mock

import dask.array as da
import numpy as np
import pytest
import xarray as xr

import satpy
from satpy import Scene
from satpy.tests.utils import (
    FAKE_FILEHANDLER_END,
    FAKE_FILEHANDLER_START,
    default_id_keys_config,
    make_cid,
    make_dataid,
    spy_decorator,
)


def _check_comp19_deps_are_loaded(scene):
    # comp19 required resampling to produce so we should have its 3 deps
    # 1. comp13
    # 2. ds5
    # 3. ds2
    loaded_ids = list(scene.keys())
    assert len(loaded_ids) == 3
    for name in ('comp13', 'ds5', 'ds2'):
        assert any(x['name'] == name for x in loaded_ids)


@pytest.mark.usefixtures("include_test_etc")
class TestScene:
    """Test the scene class."""

    def test_init(self):
        """Test scene initialization."""
        with mock.patch('satpy.scene.Scene._create_reader_instances') as cri:
            cri.return_value = {}
            Scene(filenames=['bla'], reader='blo')
            cri.assert_called_once_with(filenames=['bla'], reader='blo',
                                        reader_kwargs=None)

    def test_init_str_filename(self):
        """Test initializing with a single string as filenames."""
        pytest.raises(ValueError, Scene, reader='blo', filenames='test.nc')

    def test_start_end_times(self):
        """Test start and end times for a scene."""
        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')
        assert scene.start_time == FAKE_FILEHANDLER_START
        assert scene.end_time == FAKE_FILEHANDLER_END

    def test_init_preserve_reader_kwargs(self):
        """Test that the initialization preserves the kwargs."""
        cri = spy_decorator(Scene._create_reader_instances)
        with mock.patch('satpy.scene.Scene._create_reader_instances', cri):
            reader_kwargs = {'calibration_type': 'gsics'}
            scene = Scene(filenames=['fake1_1.txt'],
                          reader='fake1',
                          filter_parameters={'area': 'euron1'},
                          reader_kwargs=reader_kwargs)
            assert reader_kwargs is not cri.mock.call_args[1]['reader_kwargs']
            assert scene.start_time == FAKE_FILEHANDLER_START
            assert scene.end_time == FAKE_FILEHANDLER_END

    @pytest.mark.parametrize(
        ("reader", "filenames", "exp_sensors"),
        [
            ("fake1", ["fake1_1.txt"], {"fake_sensor"}),
            (None, {"fake1": ["fake1_1.txt"], "fake2_1ds": ["fake2_1ds_1.txt"]}, {"fake_sensor", "fake_sensor2"}),
        ]
    )
    def test_sensor_names_readers(self, reader, filenames, exp_sensors):
        """Test that Scene sensor_names handles different cases properly."""
        scene = Scene(reader=reader, filenames=filenames)
        assert scene.start_time == FAKE_FILEHANDLER_START
        assert scene.end_time == FAKE_FILEHANDLER_END
        assert scene.sensor_names == exp_sensors

    @pytest.mark.parametrize(
        ("include_reader", "added_sensor", "exp_sensors"),
        [
            (False, "my_sensor", {"my_sensor"}),
            (True, "my_sensor", {"my_sensor", "fake_sensor"}),
            (False, {"my_sensor"}, {"my_sensor"}),
            (True, {"my_sensor"}, {"my_sensor", "fake_sensor"}),
            (False, {"my_sensor1", "my_sensor2"}, {"my_sensor1", "my_sensor2"}),
            (True, {"my_sensor1", "my_sensor2"}, {"my_sensor1", "my_sensor2", "fake_sensor"}),
        ]
    )
    def test_sensor_names_added_datasets(self, include_reader, added_sensor, exp_sensors):
        """Test that Scene sensor_names handles contained sensors properly."""
        if include_reader:
            scene = Scene(reader="fake1", filenames=["fake1_1.txt"])
        else:
            scene = Scene()

        scene["my_ds"] = xr.DataArray([], attrs={"sensor": added_sensor})
        assert scene.sensor_names == exp_sensors

    def test_init_alone(self):
        """Test simple initialization."""
        scn = Scene()
        assert not scn._readers, 'Empty scene should not load any readers'

    def test_init_no_files(self):
        """Test that providing an empty list of filenames fails."""
        pytest.raises(ValueError, Scene, reader='viirs_sdr', filenames=[])

    def test_create_reader_instances_with_filenames(self):
        """Test creating a reader providing filenames."""
        filenames = ["bla", "foo", "bar"]
        reader_name = None
        with mock.patch('satpy.scene.load_readers') as findermock:
            Scene(filenames=filenames)
            findermock.assert_called_once_with(
                filenames=filenames,
                reader=reader_name,
                reader_kwargs=None,
            )

    def test_init_with_empty_filenames(self):
        """Test initialization with empty filename list."""
        filenames = []
        Scene(filenames=filenames)

    def test_init_with_fsfile(self):
        """Test initialisation with FSFile objects."""
        from satpy.readers import FSFile

        # We should not mock _create_reader_instances here, because in
        # https://github.com/pytroll/satpy/issues/1605 satpy fails with
        # TypeError within that method if passed an FSFile instance.
        # Instead rely on the ValueError that satpy raises if no readers
        # are found.
        # Choose random filename that doesn't exist.  Not using tempfile here,
        # because tempfile creates files and we don't want that here.
        fsf = FSFile("".join(random.choices(string.printable, k=50)))
        with pytest.raises(ValueError, match="No supported files found"):
            Scene(filenames=[fsf], reader=[])

    # TODO: Rewrite this test for the 'find_files_and_readers' function
    # def test_create_reader_instances_with_sensor(self):
    #     import satpy.scene
    #     sensors = ["bla", "foo", "bar"]
    #     filenames = None
    #     reader_name = None
    #     with mock.patch('satpy.scene.Scene._compute_metadata_from_readers'):
    #         with mock.patch('satpy.scene.load_readers') as findermock:
    #             scene = satpy.scene.Scene(sensor=sensors)
    #             findermock.assert_called_once_with(
    #                 ppp_config_dir=mock.ANY,
    #                 reader=reader_name,
    #                 filenames=filenames,
    #                 reader_kwargs=None,
    #             )

    # def test_create_reader_instances_with_sensor_and_filenames(self):
    #     import satpy.scene
    #     sensors = ["bla", "foo", "bar"]
    #     filenames = ["1", "2", "3"]
    #     reader_name = None
    #     with mock.patch('satpy.scene.Scene._compute_metadata_from_readers'):
    #         with mock.patch('satpy.scene.load_readers') as findermock:
    #             scene = satpy.scene.Scene(sensor=sensors, filenames=filenames)
    #             findermock.assert_called_once_with(
    #                 ppp_config_dir=mock.ANY,
    #                 reader=reader_name,
    #                 sensor=sensors,
    #                 filenames=filenames,
    #                 reader_kwargs=None,
    #             )

    def test_create_reader_instances_with_reader(self):
        """Test createring a reader instance providing the reader name."""
        reader = "foo"
        filenames = ["1", "2", "3"]
        with mock.patch('satpy.scene.load_readers') as findermock:
            findermock.return_value = {}
            Scene(reader=reader, filenames=filenames)
            findermock.assert_called_once_with(reader=reader,
                                               filenames=filenames,
                                               reader_kwargs=None,
                                               )

    def test_create_reader_instances_with_reader_kwargs(self):
        """Test creating a reader instance with reader kwargs."""
        from satpy.readers.yaml_reader import FileYAMLReader
        reader_kwargs = {'calibration_type': 'gsics'}
        filter_parameters = {'area': 'euron1'}
        reader_kwargs2 = {'calibration_type': 'gsics', 'filter_parameters': filter_parameters}

        rinit = spy_decorator(FileYAMLReader.create_filehandlers)
        with mock.patch('satpy.readers.yaml_reader.FileYAMLReader.create_filehandlers', rinit):
            scene = Scene(filenames=['fake1_1.txt'],
                          reader='fake1',
                          filter_parameters={'area': 'euron1'},
                          reader_kwargs=reader_kwargs)
            del scene
            assert reader_kwargs == rinit.mock.call_args[1]['fh_kwargs']
            rinit.mock.reset_mock()
            scene = Scene(filenames=['fake1_1.txt'],
                          reader='fake1',
                          reader_kwargs=reader_kwargs2)
            assert reader_kwargs == rinit.mock.call_args[1]['fh_kwargs']
            del scene

    def test_create_multiple_reader_different_kwargs(self, include_test_etc):
        """Test passing different kwargs to different readers."""
        from satpy.readers import load_reader
        with mock.patch.object(satpy.readers, 'load_reader', wraps=load_reader) as lr:
            Scene(filenames={"fake1_1ds": ["fake1_1ds_1.txt"],
                             "fake2_1ds": ["fake2_1ds_1.txt"]},
                  reader_kwargs={
                      "fake1_1ds": {"mouth": "omegna"},
                      "fake2_1ds": {"mouth": "varallo"}
                  })
            lr.assert_has_calls([
                    mock.call([os.path.join(include_test_etc, 'readers', 'fake1_1ds.yaml')], mouth="omegna"),
                    mock.call([os.path.join(include_test_etc, 'readers', 'fake2_1ds.yaml')], mouth="varallo")])

    def test_iter(self):
        """Test iteration over the scene."""
        scene = Scene()
        scene["1"] = xr.DataArray(np.arange(5))
        scene["2"] = xr.DataArray(np.arange(5))
        scene["3"] = xr.DataArray(np.arange(5))
        for x in scene:
            assert isinstance(x, xr.DataArray)

    def test_iter_by_area_swath(self):
        """Test iterating by area on a swath."""
        from pyresample.geometry import SwathDefinition
        scene = Scene()
        sd = SwathDefinition(lons=np.arange(5), lats=np.arange(5))
        scene["1"] = xr.DataArray(np.arange(5), attrs={'area': sd})
        scene["2"] = xr.DataArray(np.arange(5), attrs={'area': sd})
        scene["3"] = xr.DataArray(np.arange(5))
        for area_obj, ds_list in scene.iter_by_area():
            ds_list_names = set(ds['name'] for ds in ds_list)
            if area_obj is sd:
                assert ds_list_names == {'1', '2'}
            else:
                assert area_obj is None
                assert ds_list_names == {'3'}

    def test_bad_setitem(self):
        """Test setting an item wrongly."""
        scene = Scene()
        pytest.raises(ValueError, scene.__setitem__, '1', np.arange(5))

    def test_setitem(self):
        """Test setting an item."""
        from satpy.tests.utils import make_dataid
        scene = Scene()
        scene["1"] = ds1 = xr.DataArray(np.arange(5))
        expected_id = make_cid(**ds1.attrs)
        assert set(scene._datasets.keys()) == {expected_id}
        assert set(scene._wishlist) == {expected_id}

        did = make_dataid(name='oranges')
        scene[did] = ds1
        assert 'oranges' in scene
        nparray = np.arange(5*5).reshape(5, 5)
        with pytest.raises(ValueError):
            scene['apples'] = nparray
        assert 'apples' not in scene
        did = make_dataid(name='apples')
        scene[did] = nparray
        assert 'apples' in scene

    def test_getitem(self):
        """Test __getitem__ with names only."""
        scene = Scene()
        scene["1"] = ds1 = xr.DataArray(np.arange(5))
        scene["2"] = ds2 = xr.DataArray(np.arange(5))
        scene["3"] = ds3 = xr.DataArray(np.arange(5))
        assert scene['1'] is ds1
        assert scene['2'] is ds2
        assert scene['3'] is ds3
        pytest.raises(KeyError, scene.__getitem__, '4')
        assert scene.get('3') is ds3
        assert scene.get('4') is None

    def test_getitem_modifiers(self):
        """Test __getitem__ with names and modifiers."""
        # Return least modified item
        scene = Scene()
        scene['1'] = ds1_m0 = xr.DataArray(np.arange(5))
        scene[make_dataid(name='1', modifiers=('mod1',))
              ] = xr.DataArray(np.arange(5))
        assert scene['1'] is ds1_m0
        assert len(list(scene.keys())) == 2

        scene = Scene()
        scene['1'] = ds1_m0 = xr.DataArray(np.arange(5))
        scene[make_dataid(name='1', modifiers=('mod1',))
              ] = xr.DataArray(np.arange(5))
        scene[make_dataid(name='1', modifiers=('mod1', 'mod2'))
              ] = xr.DataArray(np.arange(5))
        assert scene['1'] is ds1_m0
        assert len(list(scene.keys())) == 3

        scene = Scene()
        scene[make_dataid(name='1', modifiers=('mod1', 'mod2'))
              ] = ds1_m2 = xr.DataArray(np.arange(5))
        scene[make_dataid(name='1', modifiers=('mod1',))
              ] = ds1_m1 = xr.DataArray(np.arange(5))
        assert scene['1'] is ds1_m1
        assert scene[make_dataid(name='1', modifiers=('mod1', 'mod2'))] is ds1_m2
        pytest.raises(KeyError, scene.__getitem__,
                      make_dataid(name='1', modifiers=tuple()))
        assert len(list(scene.keys())) == 2

    def test_getitem_slices(self):
        """Test __getitem__ with slices."""
        from pyresample.geometry import AreaDefinition, SwathDefinition
        from pyresample.utils import proj4_str_to_dict
        scene1 = Scene()
        scene2 = Scene()
        proj_dict = proj4_str_to_dict('+proj=lcc +datum=WGS84 +ellps=WGS84 '
                                      '+lon_0=-95. +lat_0=25 +lat_1=25 '
                                      '+units=m +no_defs')
        area_def = AreaDefinition(
            'test',
            'test',
            'test',
            proj_dict,
            200,
            400,
            (-1000., -1500., 1000., 1500.),
        )
        swath_def = SwathDefinition(lons=np.zeros((5, 10)),
                                    lats=np.zeros((5, 10)))
        scene1["1"] = scene2["1"] = xr.DataArray(np.zeros((5, 10)))
        scene1["2"] = scene2["2"] = xr.DataArray(np.zeros((5, 10)),
                                                 dims=('y', 'x'))
        scene1["3"] = xr.DataArray(np.zeros((5, 10)), dims=('y', 'x'),
                                   attrs={'area': area_def})
        anc_vars = [xr.DataArray(np.ones((5, 10)),
                                 attrs={'name': 'anc_var', 'area': area_def})]
        attrs = {'ancillary_variables': anc_vars, 'area': area_def}
        scene1["3a"] = xr.DataArray(np.zeros((5, 10)),
                                    dims=('y', 'x'),
                                    attrs=attrs)
        scene2["4"] = xr.DataArray(np.zeros((5, 10)), dims=('y', 'x'),
                                   attrs={'area': swath_def})
        anc_vars = [xr.DataArray(np.ones((5, 10)),
                                 attrs={'name': 'anc_var', 'area': swath_def})]
        attrs = {'ancillary_variables': anc_vars, 'area': swath_def}
        scene2["4a"] = xr.DataArray(np.zeros((5, 10)),
                                    dims=('y', 'x'),
                                    attrs=attrs)
        new_scn1 = scene1[2:5, 2:8]
        new_scn2 = scene2[2:5, 2:8]
        for new_scn in [new_scn1, new_scn2]:
            # datasets without an area don't get sliced
            assert new_scn['1'].shape == (5, 10)
            assert new_scn['2'].shape == (5, 10)

        assert new_scn1['3'].shape == (3, 6)
        assert 'area' in new_scn1['3'].attrs
        assert new_scn1['3'].attrs['area'].shape == (3, 6)
        assert new_scn1['3a'].shape == (3, 6)
        a_var = new_scn1['3a'].attrs['ancillary_variables'][0]
        assert a_var.shape == (3, 6)

        assert new_scn2['4'].shape == (3, 6)
        assert 'area' in new_scn2['4'].attrs
        assert new_scn2['4'].attrs['area'].shape == (3, 6)
        assert new_scn2['4a'].shape == (3, 6)
        a_var = new_scn2['4a'].attrs['ancillary_variables'][0]
        assert a_var.shape == (3, 6)

    def test_crop(self):
        """Test the crop method."""
        from pyresample.geometry import AreaDefinition
        scene1 = Scene()
        area_extent = (-5570248.477339745, -5561247.267842293, 5567248.074173927,
                       5570248.477339745)
        proj_dict = {'a': 6378169.0, 'b': 6356583.8, 'h': 35785831.0,
                     'lon_0': 0.0, 'proj': 'geos', 'units': 'm'}
        x_size = 3712
        y_size = 3712
        area_def = AreaDefinition(
            'test',
            'test',
            'test',
            proj_dict,
            x_size,
            y_size,
            area_extent,
        )
        area_def2 = AreaDefinition(
            'test2',
            'test2',
            'test2',
            proj_dict,
            x_size // 2,
            y_size // 2,
            area_extent,
        )
        scene1["1"] = xr.DataArray(np.zeros((y_size, x_size)))
        scene1["2"] = xr.DataArray(np.zeros((y_size, x_size)), dims=('y', 'x'))
        scene1["3"] = xr.DataArray(np.zeros((y_size, x_size)), dims=('y', 'x'),
                                   attrs={'area': area_def})
        scene1["4"] = xr.DataArray(np.zeros((y_size // 2, x_size // 2)), dims=('y', 'x'),
                                   attrs={'area': area_def2})

        # by area
        crop_area = AreaDefinition(
            'test',
            'test',
            'test',
            proj_dict,
            x_size,
            y_size,
            (area_extent[0] + 10000., area_extent[1] + 500000.,
             area_extent[2] - 10000., area_extent[3] - 500000.)
        )
        new_scn1 = scene1.crop(crop_area)
        assert '1' in new_scn1
        assert '2' in new_scn1
        assert '3' in new_scn1
        assert new_scn1['1'].shape == (y_size, x_size)
        assert new_scn1['2'].shape == (y_size, x_size)
        assert new_scn1['3'].shape == (3380, 3708)
        assert new_scn1['4'].shape == (1690, 1854)

        # by lon/lat bbox
        new_scn1 = scene1.crop(ll_bbox=(-20., -5., 0, 0))
        assert '1' in new_scn1
        assert '2' in new_scn1
        assert '3' in new_scn1
        assert new_scn1['1'].shape == (y_size, x_size)
        assert new_scn1['2'].shape == (y_size, x_size)
        assert new_scn1['3'].shape == (184, 714)
        assert new_scn1['4'].shape == (92, 357)

        # by x/y bbox
        new_scn1 = scene1.crop(xy_bbox=(-200000., -100000., 0, 0))
        assert '1' in new_scn1
        assert '2' in new_scn1
        assert '3' in new_scn1
        assert new_scn1['1'].shape == (y_size, x_size)
        assert new_scn1['2'].shape == (y_size, x_size)
        assert new_scn1['3'].shape == (36, 70)
        assert new_scn1['4'].shape == (18, 35)

    def test_crop_epsg_crs(self):
        """Test the crop method when source area uses an EPSG code."""
        from pyresample.geometry import AreaDefinition

        scene1 = Scene()
        area_extent = (699960.0, 5390220.0, 809760.0, 5500020.0)
        x_size = 3712
        y_size = 3712
        area_def = AreaDefinition(
            'test', 'test', 'test',
            "EPSG:32630",
            x_size,
            y_size,
            area_extent,
        )
        scene1["1"] = xr.DataArray(np.zeros((y_size, x_size)), dims=('y', 'x'),
                                   attrs={'area': area_def})
        # by x/y bbox
        new_scn1 = scene1.crop(xy_bbox=(719695.7781587119, 5427887.407618969, 725068.1609052602, 5433708.364368956))
        assert '1' in new_scn1
        assert new_scn1['1'].shape == (198, 182)

    def test_crop_rgb(self):
        """Test the crop method on multi-dimensional data."""
        from pyresample.geometry import AreaDefinition
        scene1 = Scene()
        area_extent = (-5570248.477339745, -5561247.267842293, 5567248.074173927,
                       5570248.477339745)
        proj_dict = {'a': 6378169.0, 'b': 6356583.8, 'h': 35785831.0,
                     'lon_0': 0.0, 'proj': 'geos', 'units': 'm'}
        x_size = 3712
        y_size = 3712
        area_def = AreaDefinition(
            'test',
            'test',
            'test',
            proj_dict,
            x_size,
            y_size,
            area_extent,
        )
        area_def2 = AreaDefinition(
            'test2',
            'test2',
            'test2',
            proj_dict,
            x_size // 2,
            y_size // 2,
            area_extent,
            )
        scene1["1"] = xr.DataArray(np.zeros((3, y_size, x_size)),
                                   dims=('bands', 'y', 'x'),
                                   attrs={'area': area_def})
        scene1["2"] = xr.DataArray(np.zeros((y_size // 2, 3, x_size // 2)),
                                   dims=('y', 'bands', 'x'),
                                   attrs={'area': area_def2})

        # by lon/lat bbox
        new_scn1 = scene1.crop(ll_bbox=(-20., -5., 0, 0))
        assert '1' in new_scn1
        assert '2' in new_scn1
        assert 'bands' in new_scn1['1'].dims
        assert 'bands' in new_scn1['2'].dims
        assert new_scn1['1'].shape == (3, 184, 714)
        assert new_scn1['2'].shape == (92, 3, 357)

    def test_contains(self):
        """Test contains."""
        scene = Scene()
        scene["1"] = xr.DataArray(np.arange(5),
                                  attrs={'wavelength': (0.1, 0.2, 0.3),
                                         '_satpy_id_keys': default_id_keys_config})
        assert '1' in scene
        assert 0.15 in scene
        assert '2' not in scene
        assert 0.31 not in scene

        scene = Scene()
        scene['blueberry'] = xr.DataArray(np.arange(5))
        scene['blackberry'] = xr.DataArray(np.arange(5))
        scene['strawberry'] = xr.DataArray(np.arange(5))
        scene['raspberry'] = xr.DataArray(np.arange(5))
        #  deepcode ignore replace~keys~list~compare: This is on purpose
        assert make_cid(name='blueberry') in scene.keys()
        assert make_cid(name='blueberry') in scene
        assert 'blueberry' in scene
        assert 'blueberry' not in scene.keys()

    def test_delitem(self):
        """Test deleting an item."""
        scene = Scene()
        scene["1"] = xr.DataArray(np.arange(5),
                                  attrs={'wavelength': (0.1, 0.2, 0.3),
                                         '_satpy_id_keys': default_id_keys_config})
        scene["2"] = xr.DataArray(np.arange(5),
                                  attrs={'wavelength': (0.4, 0.5, 0.6),
                                         '_satpy_id_keys': default_id_keys_config})
        scene["3"] = xr.DataArray(np.arange(5),
                                  attrs={'wavelength': (0.7, 0.8, 0.9),
                                         '_satpy_id_keys': default_id_keys_config})
        del scene['1']
        del scene['3']
        del scene[0.45]
        assert not scene._wishlist
        assert not list(scene._datasets.keys())
        pytest.raises(KeyError, scene.__delitem__, 0.2)

    def test_all_datasets_no_readers(self):
        """Test all datasets with no reader."""
        scene = Scene()
        pytest.raises(KeyError, scene.all_dataset_ids, reader_name='fake')
        id_list = scene.all_dataset_ids()
        assert id_list == []
        # no sensors are loaded so we shouldn't get any comps either
        id_list = scene.all_dataset_ids(composites=True)
        assert id_list == []

    def test_all_dataset_names_no_readers(self):
        """Test all dataset names with no reader."""
        scene = Scene()
        pytest.raises(KeyError, scene.all_dataset_names, reader_name='fake')
        name_list = scene.all_dataset_names()
        assert name_list == []
        # no sensors are loaded so we shouldn't get any comps either
        name_list = scene.all_dataset_names(composites=True)
        assert name_list == []

    def test_available_dataset_no_readers(self):
        """Test the available datasets without a reader."""
        scene = Scene()
        pytest.raises(
            KeyError, scene.available_dataset_ids, reader_name='fake')
        name_list = scene.available_dataset_ids()
        assert name_list == []
        # no sensors are loaded so we shouldn't get any comps either
        name_list = scene.available_dataset_ids(composites=True)
        assert name_list == []

    def test_available_dataset_names_no_readers(self):
        """Test the available dataset names without a reader."""
        scene = Scene()
        pytest.raises(
            KeyError, scene.available_dataset_names, reader_name='fake')
        name_list = scene.available_dataset_names()
        assert name_list == []
        # no sensors are loaded so we shouldn't get any comps either
        name_list = scene.available_dataset_names(composites=True)
        assert name_list == []

    def test_storage_options_from_reader_kwargs_no_options(self):
        """Test getting storage options from reader kwargs.

        Case where there are no options given.
        """
        filenames = ["s3://data-bucket/file1", "s3://data-bucket/file2", "s3://data-bucket/file3"]
        with mock.patch('satpy.scene.load_readers'):
            with mock.patch('fsspec.open_files') as open_files:
                Scene(filenames=filenames)
                open_files.assert_called_once_with(filenames)

    def test_storage_options_from_reader_kwargs_single_dict_no_options(self):
        """Test getting storage options from reader kwargs for remote files.

        Case where a single dict is given for all readers without storage options.
        """
        filenames = ["s3://data-bucket/file1", "s3://data-bucket/file2", "s3://data-bucket/file3"]
        reader_kwargs = {'reader_opt': 'foo'}
        with mock.patch('satpy.scene.load_readers'):
            with mock.patch('fsspec.open_files') as open_files:
                Scene(filenames=filenames, reader_kwargs=reader_kwargs)
                open_files.assert_called_once_with(filenames)

    @pytest.mark.parametrize("reader_kwargs", [{}, {'reader_opt': 'foo'}])
    def test_storage_options_from_reader_kwargs_single_dict(self, reader_kwargs):
        """Test getting storage options from reader kwargs.

        Case where a single dict is given for all readers with some common storage options.
        """
        filenames = ["s3://data-bucket/file1", "s3://data-bucket/file2", "s3://data-bucket/file3"]
        expected_reader_kwargs = reader_kwargs.copy()
        storage_options = {'option1': '1'}
        reader_kwargs['storage_options'] = storage_options
        orig_reader_kwargs = deepcopy(reader_kwargs)
        with mock.patch('satpy.scene.load_readers') as load_readers:
            with mock.patch('fsspec.open_files') as open_files:
                Scene(filenames=filenames, reader_kwargs=reader_kwargs)
                call_ = load_readers.mock_calls[0]
                assert call_.kwargs['reader_kwargs'] == expected_reader_kwargs
                open_files.assert_called_once_with(filenames, **storage_options)
                assert reader_kwargs == orig_reader_kwargs

    def test_storage_options_from_reader_kwargs_per_reader(self):
        """Test getting storage options from reader kwargs.

        Case where each reader have their own storage options.
        """
        filenames = {
            "reader1": ["s3://data-bucket/file1"],
            "reader2": ["s3://data-bucket/file2"],
            "reader3": ["s3://data-bucket/file3"],
        }
        storage_options_1 = {'option1': '1'}
        storage_options_2 = {'option2': '2'}
        storage_options_3 = {'option3': '3'}
        reader_kwargs = {
            "reader1": {'reader_opt_1': 'foo'},
            "reader2": {'reader_opt_2': 'bar'},
            "reader3": {'reader_opt_3': 'baz'},
        }
        expected_reader_kwargs = deepcopy(reader_kwargs)
        reader_kwargs['reader1']['storage_options'] = storage_options_1
        reader_kwargs['reader2']['storage_options'] = storage_options_2
        reader_kwargs['reader3']['storage_options'] = storage_options_3
        orig_reader_kwargs = deepcopy(reader_kwargs)

        with mock.patch('satpy.scene.load_readers') as load_readers:
            with mock.patch('fsspec.open_files') as open_files:
                Scene(filenames=filenames, reader_kwargs=reader_kwargs)
                call_ = load_readers.mock_calls[0]
                assert call_.kwargs['reader_kwargs'] == expected_reader_kwargs
                assert mock.call(filenames["reader1"], **storage_options_1) in open_files.mock_calls
                assert mock.call(filenames["reader2"], **storage_options_2) in open_files.mock_calls
                assert mock.call(filenames["reader3"], **storage_options_3) in open_files.mock_calls
                assert reader_kwargs == orig_reader_kwargs

    def test_storage_options_from_reader_kwargs_per_reader_and_global(self):
        """Test getting storage options from reader kwargs.

        Case where each reader have their own storage options and there are
        global options to merge.
        """
        filenames = {
            "reader1": ["s3://data-bucket/file1"],
            "reader2": ["s3://data-bucket/file2"],
            "reader3": ["s3://data-bucket/file3"],
        }
        reader_kwargs = {
            "reader1": {'reader_opt_1': 'foo', 'storage_options': {'option1': '1'}},
            "reader2": {'reader_opt_2': 'bar', 'storage_options': {'option2': '2'}},
            "storage_options": {"endpoint_url": "url"},
        }
        orig_reader_kwargs = deepcopy(reader_kwargs)

        with mock.patch('satpy.scene.load_readers'):
            with mock.patch('fsspec.open_files') as open_files:
                Scene(filenames=filenames, reader_kwargs=reader_kwargs)
                assert mock.call(filenames["reader1"], option1='1', endpoint_url='url') in open_files.mock_calls
                assert mock.call(filenames["reader2"], option2='2', endpoint_url='url') in open_files.mock_calls
                assert reader_kwargs == orig_reader_kwargs


def _create_coarest_finest_data_array(shape, area_def, attrs=None):
    data_arr = xr.DataArray(
        da.arange(math.prod(shape)).reshape(shape),
        attrs={
            'area': area_def,
        })
    if attrs:
        data_arr.attrs.update(attrs)
    return data_arr


def _create_coarsest_finest_area_def(shape, extents):
    from pyresample import AreaDefinition
    proj_str = '+proj=lcc +datum=WGS84 +ellps=WGS84 +lon_0=-95. +lat_0=25 +lat_1=25 +units=m +no_defs'
    area_def = AreaDefinition(
        'test',
        'test',
        'test',
        proj_str,
        shape[1],
        shape[0],
        extents,
    )
    return area_def


def _create_coarsest_finest_swath_def(shape, extents, name_suffix):
    from pyresample import SwathDefinition
    if len(shape) == 1:
        lons_arr = da.linspace(extents[0], extents[2], shape[0], dtype=np.float32)
        lats_arr = da.linspace(extents[1], extents[3], shape[0], dtype=np.float32)
    else:
        lons_arr = da.repeat(da.linspace(extents[0], extents[2], shape[1], dtype=np.float32)[None, :], shape[0], axis=0)
        lats_arr = da.repeat(da.linspace(extents[1], extents[3], shape[0], dtype=np.float32)[:, None], shape[1], axis=1)
    lons_data_arr = xr.DataArray(lons_arr, attrs={"name": f"longitude{name_suffix}"})
    lats_data_arr = xr.DataArray(lats_arr, attrs={"name": f"latitude1{name_suffix}"})
    return SwathDefinition(lons_data_arr, lats_data_arr)


class TestFinestCoarsestArea:
    """Test the Scene logic for finding the finest and coarsest area."""

    @pytest.mark.parametrize(
        ("coarse_area", "fine_area"),
        [
            (_create_coarsest_finest_area_def((2, 5), (1000.0, 1500.0, -1000.0, -1500.0)),
             _create_coarsest_finest_area_def((4, 10), (1000.0, 1500.0, -1000.0, -1500.0))),
            (_create_coarsest_finest_area_def((2, 5), (-1000.0, -1500.0, 1000.0, 1500.0)),
             _create_coarsest_finest_area_def((4, 10), (-1000.0, -1500.0, 1000.0, 1500.0))),
            (_create_coarsest_finest_swath_def((2, 5), (1000.0, 1500.0, -1000.0, -1500.0), "1"),
             _create_coarsest_finest_swath_def((4, 10), (1000.0, 1500.0, -1000.0, -1500.0), "1")),
            (_create_coarsest_finest_swath_def((5,), (1000.0, 1500.0, -1000.0, -1500.0), "1"),
             _create_coarsest_finest_swath_def((10,), (1000.0, 1500.0, -1000.0, -1500.0), "1")),
        ]
    )
    def test_coarsest_finest_area_different_shape(self, coarse_area, fine_area):
        """Test 'coarsest_area' and 'finest_area' methods for upright areas."""
        ds1 = _create_coarest_finest_data_array(coarse_area.shape, coarse_area, {"wavelength": (0.1, 0.2, 0.3)})
        ds2 = _create_coarest_finest_data_array(fine_area.shape, fine_area, {"wavelength": (0.4, 0.5, 0.6)})
        ds3 = _create_coarest_finest_data_array(fine_area.shape, fine_area, {"wavelength": (0.7, 0.8, 0.9)})
        scn = Scene()
        scn["1"] = ds1
        scn["2"] = ds2
        scn["3"] = ds3

        assert scn.coarsest_area() is coarse_area
        assert scn.finest_area() is fine_area
        assert scn.coarsest_area(['2', '3']) is fine_area

    @pytest.mark.parametrize(
        ("area_def", "shifted_area"),
        [
            (_create_coarsest_finest_area_def((2, 5), (-1000.0, -1500.0, 1000.0, 1500.0)),
             _create_coarsest_finest_area_def((2, 5), (-900.0, -1400.0, 1100.0, 1600.0))),
            (_create_coarsest_finest_swath_def((2, 5), (-1000.0, -1500.0, 1000.0, 1500.0), "1"),
             _create_coarsest_finest_swath_def((2, 5), (-900.0, -1400.0, 1100.0, 1600.0), "2")),
        ],
    )
    def test_coarsest_finest_area_same_shape(self, area_def, shifted_area):
        """Test that two areas with the same shape are consistently returned.

        If two geometries (ex. two AreaDefinitions or two SwathDefinitions)
        have the same resolution (shape) but different
        coordinates, which one has the finer resolution would ultimately be
        determined by the semi-random ordering of the internal container of
        the Scene (a dict) if only pixel resolution was compared. This test
        makes sure that it is always the same object returned.

        """
        ds1 = _create_coarest_finest_data_array(area_def.shape, area_def)
        ds2 = _create_coarest_finest_data_array(area_def.shape, shifted_area)
        scn = Scene()
        scn["ds1"] = ds1
        scn["ds2"] = ds2
        course_area1 = scn.coarsest_area()

        scn = Scene()
        scn["ds2"] = ds2
        scn["ds1"] = ds1
        coarse_area2 = scn.coarsest_area()
        # doesn't matter what order they were added, this should be the same area
        assert coarse_area2 is course_area1


@pytest.mark.usefixtures("include_test_etc")
class TestSceneSerialization:
    """Test the Scene serialization."""

    def test_serialization_with_readers_and_data_arr(self):
        """Test that dask can serialize a Scene with readers."""
        from distributed.protocol import deserialize, serialize

        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')
        scene.load(['ds1'])
        cloned_scene = deserialize(*serialize(scene))
        assert scene._readers.keys() == cloned_scene._readers.keys()
        assert scene.all_dataset_ids == scene.all_dataset_ids


@pytest.mark.usefixtures("include_test_etc")
class TestSceneResampling:
    """Test resampling a Scene to another Scene object."""

    def _fake_resample_dataset(self, dataset, dest_area, **kwargs):
        """Return copy of dataset pretending it was resampled."""
        return dataset.copy()

    def _fake_resample_dataset_force_20x20(self, dataset, dest_area, **kwargs):
        """Return copy of dataset pretending it was resampled to (20, 20) shape."""
        data = np.zeros((20, 20))
        attrs = dataset.attrs.copy()
        attrs['area'] = dest_area
        return xr.DataArray(
            data,
            dims=('y', 'x'),
            attrs=attrs,
        )

    @mock.patch('satpy.scene.resample_dataset')
    @pytest.mark.parametrize('datasets', [
        None,
        ('comp13', 'ds5', 'ds2'),
    ])
    def test_resample_scene_copy(self, rs, datasets):
        """Test that the Scene is properly copied during resampling.

        The Scene that is created as a copy of the original Scene should not
        be able to affect the original Scene object.

        """
        from pyresample.geometry import AreaDefinition
        rs.side_effect = self._fake_resample_dataset_force_20x20

        proj_str = ('+proj=lcc +datum=WGS84 +ellps=WGS84 '
                    '+lon_0=-95. +lat_0=25 +lat_1=25 +units=m +no_defs')
        area_def = AreaDefinition('test', 'test', 'test', proj_str, 5, 5, (-1000., -1500., 1000., 1500.))
        area_def.get_area_slices = mock.MagicMock()
        scene = Scene(filenames=['fake1_1.txt', 'fake1_highres_1.txt'], reader='fake1')

        scene.load(['comp19'])
        new_scene = scene.resample(area_def, datasets=datasets)
        new_scene['new_ds'] = new_scene['comp19'].copy()

        scene.load(['ds1'])

        comp19_node = scene._dependency_tree['comp19']
        ds5_mod_id = make_dataid(name='ds5', modifiers=('res_change',))
        ds5_node = scene._dependency_tree[ds5_mod_id]
        comp13_node = scene._dependency_tree['comp13']

        assert comp13_node.data[1][0] is comp19_node.data[1][0]
        assert comp13_node.data[1][0] is ds5_node
        pytest.raises(KeyError, scene._dependency_tree.__getitem__, 'new_ds')

        # comp19 required resampling to produce so we should have its 3 deps
        # 1. comp13
        # 2. ds5
        # 3. ds2
        # Then we loaded ds1 separately so we should have
        # 4. ds1
        loaded_ids = list(scene.keys())
        assert len(loaded_ids) == 4
        for name in ('comp13', 'ds5', 'ds2', 'ds1'):
            assert any(x['name'] == name for x in loaded_ids)

        loaded_ids = list(new_scene.keys())
        assert len(loaded_ids) == 2
        assert loaded_ids[0] == make_cid(name='comp19')
        assert loaded_ids[1] == make_cid(name='new_ds')

    @mock.patch('satpy.scene.resample_dataset')
    def test_resample_scene_preserves_requested_dependencies(self, rs):
        """Test that the Scene is properly copied during resampling.

        The Scene that is created as a copy of the original Scene should not
        be able to affect the original Scene object.

        """
        from pyresample.geometry import AreaDefinition
        from pyresample.utils import proj4_str_to_dict

        rs.side_effect = self._fake_resample_dataset
        proj_dict = proj4_str_to_dict('+proj=lcc +datum=WGS84 +ellps=WGS84 '
                                      '+lon_0=-95. +lat_0=25 +lat_1=25 '
                                      '+units=m +no_defs')
        area_def = AreaDefinition('test', 'test', 'test', proj_dict, 5, 5, (-1000., -1500., 1000., 1500.))
        area_def.get_area_slices = mock.MagicMock()
        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')

        # Set PYTHONHASHSEED to 0 in the interpreter to test as intended (comp26 comes before comp14)
        scene.load(['comp26', 'comp14'], generate=False)
        scene.resample(area_def, unload=True)
        new_scene_2 = scene.resample(area_def, unload=True)

        assert 'comp14' not in scene
        assert 'comp26' not in scene
        assert 'comp14' in new_scene_2
        assert 'comp26' in new_scene_2
        assert 'ds1' not in new_scene_2  # unloaded

    @mock.patch('satpy.scene.resample_dataset')
    def test_resample_reduce_data_toggle(self, rs):
        """Test that the Scene can be reduced or not reduced during resampling."""
        from pyresample.geometry import AreaDefinition

        rs.side_effect = self._fake_resample_dataset_force_20x20
        proj_str = ('+proj=lcc +datum=WGS84 +ellps=WGS84 '
                    '+lon_0=-95. +lat_0=25 +lat_1=25 +units=m +no_defs')
        target_area = AreaDefinition('test', 'test', 'test', proj_str, 4, 4, (-1000., -1500., 1000., 1500.))
        area_def = AreaDefinition('test', 'test', 'test', proj_str, 5, 5, (-1000., -1500., 1000., 1500.))
        area_def.get_area_slices = mock.MagicMock()
        get_area_slices = area_def.get_area_slices
        get_area_slices.return_value = (slice(0, 3, None), slice(0, 3, None))
        area_def_big = AreaDefinition('test', 'test', 'test', proj_str, 10, 10, (-1000., -1500., 1000., 1500.))
        area_def_big.get_area_slices = mock.MagicMock()
        get_area_slices_big = area_def_big.get_area_slices
        get_area_slices_big.return_value = (slice(0, 6, None), slice(0, 6, None))

        # Test that data reduction can be disabled
        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')
        scene.load(['comp19'])
        scene['comp19'].attrs['area'] = area_def
        scene['comp19_big'] = xr.DataArray(
            da.zeros((10, 10)), dims=('y', 'x'),
            attrs=scene['comp19'].attrs.copy())
        scene['comp19_big'].attrs['area'] = area_def_big
        scene['comp19_copy'] = scene['comp19'].copy()
        orig_slice_data = scene._slice_data
        # we force the below order of processing to test that success isn't
        # based on data of the same resolution being processed together
        test_order = [
            make_cid(**scene['comp19'].attrs),
            make_cid(**scene['comp19_big'].attrs),
            make_cid(**scene['comp19_copy'].attrs),
        ]
        with mock.patch('satpy.scene.Scene._slice_data') as slice_data, \
                mock.patch('satpy.dataset.dataset_walker') as ds_walker:
            ds_walker.return_value = test_order
            slice_data.side_effect = orig_slice_data
            scene.resample(target_area, reduce_data=False)
            assert not slice_data.called
            assert not get_area_slices.called
            scene.resample(target_area)
            assert slice_data.called_once
            assert get_area_slices.called_once
            scene.resample(target_area, reduce_data=True)
            # 2 times for each dataset
            # once for default (reduce_data=True)
            # once for kwarg forced to `True`
            assert slice_data.call_count == 2 * 3
            assert get_area_slices.called_once

    def test_resample_ancillary(self):
        """Test that the Scene reducing data does not affect final output."""
        from pyresample.geometry import AreaDefinition
        from pyresample.utils import proj4_str_to_dict
        proj_dict = proj4_str_to_dict('+proj=lcc +datum=WGS84 +ellps=WGS84 '
                                      '+lon_0=-95. +lat_0=25 +lat_1=25 '
                                      '+units=m +no_defs')
        area_def = AreaDefinition('test', 'test', 'test', proj_dict, 5, 5, (-1000., -1500., 1000., 1500.))
        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')

        scene.load(['comp19', 'comp20'])
        scene['comp19'].attrs['area'] = area_def
        scene['comp19'].attrs['ancillary_variables'] = [scene['comp20']]
        scene['comp20'].attrs['area'] = area_def

        dst_area = AreaDefinition('dst', 'dst', 'dst',
                                  proj_dict,
                                  2, 2,
                                  (-1000., -1500., 0., 0.),
                                  )
        new_scene = scene.resample(dst_area)
        assert new_scene['comp20'] is new_scene['comp19'].attrs['ancillary_variables'][0]

    def test_resample_multi_ancillary(self):
        """Test that multiple ancillary variables are retained after resampling.

        This test corresponds to GH#2329
        """
        from pyresample import create_area_def
        sc = Scene()
        n = 5
        ar = create_area_def("a", 4087, resolution=1000, center=(0, 0), shape=(n, n))
        anc_vars = [xr.DataArray(
            np.arange(n*n).reshape(n, n)*i,
            dims=("y", "x"),
            attrs={"name": f"anc{i:d}", "area": ar}) for i in range(2)]
        sc["test"] = xr.DataArray(
            np.arange(n*n).reshape(n, n),
            dims=("y", "x"),
            attrs={
                "area": ar,
                "name": "test",
                "ancillary_variables": anc_vars})
        subset = create_area_def("b", 4087, resolution=800, center=(0, 0),
                                 shape=(n-1, n-1))
        ls = sc.resample(subset)
        assert ([av.attrs["name"] for av in sc["test"].attrs["ancillary_variables"]] ==
                [av.attrs["name"] for av in ls["test"].attrs["ancillary_variables"]])

    def test_resample_reduce_data(self):
        """Test that the Scene reducing data does not affect final output."""
        from pyresample.geometry import AreaDefinition
        proj_str = ('+proj=lcc +datum=WGS84 +ellps=WGS84 '
                    '+lon_0=-95. +lat_0=25 +lat_1=25 +units=m +no_defs')
        area_def = AreaDefinition('test', 'test', 'test', proj_str, 20, 20, (-1000., -1500., 1000., 1500.))
        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')

        scene.load(['comp19'])
        scene['comp19'].attrs['area'] = area_def
        dst_area = AreaDefinition('dst', 'dst', 'dst',
                                  proj_str,
                                  20, 20,
                                  (-1000., -1500., 0., 0.),
                                  )
        new_scene1 = scene.resample(dst_area, reduce_data=False)
        new_scene2 = scene.resample(dst_area)
        new_scene3 = scene.resample(dst_area, reduce_data=True)
        assert new_scene1['comp19'].shape == (20, 20, 3)
        assert new_scene2['comp19'].shape == (20, 20, 3)
        assert new_scene3['comp19'].shape == (20, 20, 3)

    @mock.patch('satpy.scene.resample_dataset')
    def test_no_generate_comp10(self, rs):
        """Test generating a composite after loading."""
        from pyresample.geometry import AreaDefinition
        from pyresample.utils import proj4_str_to_dict

        rs.side_effect = self._fake_resample_dataset
        proj_dict = proj4_str_to_dict('+proj=lcc +datum=WGS84 +ellps=WGS84 '
                                      '+lon_0=-95. +lat_0=25 +lat_1=25 '
                                      '+units=m +no_defs')
        area_def = AreaDefinition(
            'test',
            'test',
            'test',
            proj_dict,
            200,
            400,
            (-1000., -1500., 1000., 1500.),
        )

        # it is fine that an optional prereq doesn't exist
        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')
        scene.load(['comp10'], generate=False)
        assert any(ds_id['name'] == 'comp10' for ds_id in scene._wishlist)
        assert 'comp10' not in scene
        # two dependencies should have been loaded
        assert len(scene._datasets) == 2
        assert len(scene.missing_datasets) == 1

        new_scn = scene.resample(area_def, generate=False)
        assert 'comp10' not in scene
        # two dependencies should have been loaded
        assert len(scene._datasets) == 2
        assert len(scene.missing_datasets) == 1

        new_scn._generate_composites_from_loaded_datasets()
        assert any(ds_id['name'] == 'comp10' for ds_id in new_scn._wishlist)
        assert 'comp10' in new_scn
        assert not new_scn.missing_datasets

        # try generating them right away
        new_scn = scene.resample(area_def)
        assert any(ds_id['name'] == 'comp10' for ds_id in new_scn._wishlist)
        assert 'comp10' in new_scn
        assert not new_scn.missing_datasets

    def test_comp_loading_after_resampling_existing_sensor(self):
        """Test requesting a composite after resampling."""
        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')
        scene.load(["ds1", "ds2"])
        new_scn = scene.resample(resampler='native')

        # Can't load from readers after resampling
        with pytest.raises(KeyError):
            new_scn.load(["ds3"])

        # But we can load composites because the sensor composites were loaded
        # when the reader datasets were accessed
        new_scn.load(["comp2"])
        assert "comp2" in new_scn

    def test_comp_loading_after_resampling_new_sensor(self):
        """Test requesting a composite after resampling when the sensor composites weren't loaded before."""
        # this is our base Scene with sensor "fake_sensor2"
        scene1 = Scene(filenames=['fake2_3ds_1.txt'], reader='fake2_3ds')
        scene1.load(["ds2"])
        new_scn = scene1.resample(resampler='native')

        # Can't load from readers after resampling
        with pytest.raises(KeyError):
            new_scn.load(["ds3"])

        # Can't load the composite from fake_sensor composites yet
        # 'ds1' is missing
        with pytest.raises(KeyError):
            new_scn.load(["comp2"])

        # artificial DataArray "created by the user"
        # mimics a user adding their own data with the same sensor
        user_da = scene1["ds2"].copy()
        user_da.attrs["name"] = "ds1"
        user_da.attrs["sensor"] = {"fake_sensor2"}
        # Add 'ds1' that doesn't provide the 'fake_sensor' sensor
        new_scn["ds1"] = user_da
        with pytest.raises(KeyError):
            new_scn.load(["comp2"])
        assert "comp2" not in new_scn

        # artificial DataArray "created by the user"
        # mimics a user adding their own data with its own sensor to the Scene
        user_da = scene1["ds2"].copy()
        user_da.attrs["name"] = "ds1"
        user_da.attrs["sensor"] = {"fake_sensor"}
        # Now 'fake_sensor' composites have been loaded
        new_scn["ds1"] = user_da
        new_scn.load(["comp2"])
        assert "comp2" in new_scn

    def test_comp_loading_multisensor_composite_created_user(self):
        """Test that multisensor composite can be created manually.

        Test that if the user has created datasets "manually", that
        multi-sensor composites provided can still be read.
        """
        scene1 = Scene(filenames=["fake1_1.txt"], reader="fake1")
        scene1.load(["ds1"])
        scene2 = Scene(filenames=["fake4_1.txt"], reader="fake4")
        scene2.load(["ds4_b"])
        scene3 = Scene()
        scene3["ds1"] = scene1["ds1"]
        scene3["ds4_b"] = scene2["ds4_b"]
        scene3.load(["comp_multi"])
        assert "comp_multi" in scene3

    def test_comps_need_resampling_optional_mod_deps(self):
        """Test that a composite with complex dependencies.

        This is specifically testing the case where a compositor depends on
        multiple resolution prerequisites which themselves are composites.
        These sub-composites depend on data with a modifier that only has
        optional dependencies. This is a very specific use case and is the
        simplest way to present the problem (so far).

        The general issue is that the Scene loading creates the "ds13"
        dataset which already has one modifier on it. The "comp27"
        composite requires resampling so its 4 prerequisites + the
        requested "ds13" (from the reader which includes mod1 modifier)
        remain. If the DependencyTree is not copied properly in this
        situation then the new Scene object will have the composite
        dependencies without resolution in its dep tree, but have
        the DataIDs with the resolution in the dataset dictionary.
        This all results in the Scene trying to regenerate composite
        dependencies that aren't needed which fail.

        """
        scene = Scene(filenames=['fake1_1.txt'], reader='fake1')
        # should require resampling
        scene.load(['comp27', 'ds13'])
        assert 'comp27' not in scene
        assert 'ds13' in scene

        new_scene = scene.resample(resampler='native')
        assert len(list(new_scene.keys())) == 2
        assert 'comp27' in new_scene
        assert 'ds13' in new_scene


class TestSceneSaving(unittest.TestCase):
    """Test the Scene's saving method."""

    def setUp(self):
        """Create temporary directory to save files to."""
        import tempfile
        self.base_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove the temporary directory created for a test."""
        try:
            import shutil
            shutil.rmtree(self.base_dir, ignore_errors=True)
        except OSError:
            pass

    def test_save_datasets_default(self):
        """Save a dataset using 'save_datasets'."""
        ds1 = xr.DataArray(
            da.zeros((100, 200), chunks=50),
            dims=('y', 'x'),
            attrs={'name': 'test',
                   'start_time': datetime(2018, 1, 1, 0, 0, 0)}
        )
        scn = Scene()
        scn['test'] = ds1
        scn.save_datasets(base_dir=self.base_dir)
        assert os.path.isfile(os.path.join(self.base_dir, 'test_20180101_000000.tif'))

    def test_save_datasets_by_ext(self):
        """Save a dataset using 'save_datasets' with 'filename'."""
        ds1 = xr.DataArray(
            da.zeros((100, 200), chunks=50),
            dims=('y', 'x'),
            attrs={'name': 'test',
                   'start_time': datetime(2018, 1, 1, 0, 0, 0)}
        )
        scn = Scene()
        scn['test'] = ds1

        from satpy.writers.simple_image import PillowWriter
        save_image_mock = spy_decorator(PillowWriter.save_image)
        with mock.patch.object(PillowWriter, 'save_image', save_image_mock):
            scn.save_datasets(base_dir=self.base_dir, filename='{name}.png')
        save_image_mock.mock.assert_called_once()
        assert os.path.isfile(os.path.join(self.base_dir, 'test.png'))

    def test_save_datasets_bad_writer(self):
        """Save a dataset using 'save_datasets' and a bad writer."""
        ds1 = xr.DataArray(
            da.zeros((100, 200), chunks=50),
            dims=('y', 'x'),
            attrs={'name': 'test',
                   'start_time': datetime.utcnow()}
        )
        scn = Scene()
        scn['test'] = ds1
        pytest.raises(ValueError,
                      scn.save_datasets,
                      writer='_bad_writer_',
                      base_dir=self.base_dir)

    def test_save_datasets_missing_wishlist(self):
        """Calling 'save_datasets' with no valid datasets."""
        scn = Scene()
        scn._wishlist.add(make_cid(name='true_color'))
        pytest.raises(RuntimeError,
                      scn.save_datasets,
                      writer='geotiff',
                      base_dir=self.base_dir)
        pytest.raises(KeyError,
                      scn.save_datasets,
                      datasets=['no_exist'])

    def test_save_dataset_default(self):
        """Save a dataset using 'save_dataset'."""
        ds1 = xr.DataArray(
            da.zeros((100, 200), chunks=50),
            dims=('y', 'x'),
            attrs={'name': 'test',
                   'start_time': datetime(2018, 1, 1, 0, 0, 0)}
        )
        scn = Scene()
        scn['test'] = ds1
        scn.save_dataset('test', base_dir=self.base_dir)
        assert os.path.isfile(os.path.join(self.base_dir, 'test_20180101_000000.tif'))


class TestSceneConversions(unittest.TestCase):
    """Test Scene conversion to geoviews, xarray, etc."""

    def test_to_xarray_dataset_with_empty_scene(self):
        """Test converting empty Scene to xarray dataset."""
        scn = Scene()
        xrds = scn.to_xarray_dataset()
        assert isinstance(xrds, xr.Dataset)
        assert len(xrds.variables) == 0
        assert len(xrds.coords) == 0

    def test_geoviews_basic_with_area(self):
        """Test converting a Scene to geoviews with an AreaDefinition."""
        from pyresample.geometry import AreaDefinition
        scn = Scene()
        area = AreaDefinition('test', 'test', 'test',
                              {'proj': 'geos', 'lon_0': -95.5, 'h': 35786023.0},
                              2, 2, [-200, -200, 200, 200])
        scn['ds1'] = xr.DataArray(da.zeros((2, 2), chunks=-1), dims=('y', 'x'),
                                  attrs={'start_time': datetime(2018, 1, 1),
                                         'area': area})
        gv_obj = scn.to_geoviews()
        # we assume that if we got something back, geoviews can use it
        assert gv_obj is not None

    def test_geoviews_basic_with_swath(self):
        """Test converting a Scene to geoviews with a SwathDefinition."""
        from pyresample.geometry import SwathDefinition
        scn = Scene()
        lons = xr.DataArray(da.zeros((2, 2)))
        lats = xr.DataArray(da.zeros((2, 2)))
        area = SwathDefinition(lons, lats)
        scn['ds1'] = xr.DataArray(da.zeros((2, 2), chunks=-1), dims=('y', 'x'),
                                  attrs={'start_time': datetime(2018, 1, 1),
                                         'area': area})
        gv_obj = scn.to_geoviews()
        # we assume that if we got something back, geoviews can use it
        assert gv_obj is not None


class TestSceneAggregation(unittest.TestCase):
    """Test the scene's aggregate method."""

    def test_aggregate(self):
        """Test the aggregate method."""
        x_size = 3712
        y_size = 3712

        scene1 = self._create_test_data(x_size, y_size)

        scene2 = scene1.aggregate(func='sum', x=2, y=2)
        expected_aggregated_shape = (y_size / 2, x_size / 2)
        self._check_aggregation_results(expected_aggregated_shape, scene1, scene2, x_size, y_size)

    @staticmethod
    def _create_test_data(x_size, y_size):
        from pyresample.geometry import AreaDefinition
        scene1 = Scene()
        area_extent = (-5570248.477339745, -5561247.267842293, 5567248.074173927,
                       5570248.477339745)
        proj_dict = {'a': 6378169.0, 'b': 6356583.8, 'h': 35785831.0,
                     'lon_0': 0.0, 'proj': 'geos', 'units': 'm'}
        area_def = AreaDefinition(
            'test',
            'test',
            'test',
            proj_dict,
            x_size,
            y_size,
            area_extent,
        )
        scene1["1"] = xr.DataArray(np.ones((y_size, x_size)),
                                   attrs={'_satpy_id_keys': default_id_keys_config})
        scene1["2"] = xr.DataArray(np.ones((y_size, x_size)),
                                   dims=('y', 'x'),
                                   attrs={'_satpy_id_keys': default_id_keys_config})
        scene1["3"] = xr.DataArray(np.ones((y_size, x_size)),
                                   dims=('y', 'x'),
                                   attrs={'area': area_def, '_satpy_id_keys': default_id_keys_config})
        scene1["4"] = xr.DataArray(np.ones((y_size, x_size)),
                                   dims=('y', 'x'),
                                   attrs={'area': area_def, 'standard_name': 'backscatter',
                                          '_satpy_id_keys': default_id_keys_config})
        return scene1

    def _check_aggregation_results(self, expected_aggregated_shape, scene1, scene2, x_size, y_size):
        assert scene1['1'] is scene2['1']
        assert scene1['2'] is scene2['2']
        np.testing.assert_allclose(scene2['3'].data, 4)
        assert scene2['1'].shape == (y_size, x_size)
        assert scene2['2'].shape == (y_size, x_size)
        assert scene2['3'].shape == expected_aggregated_shape
        assert 'standard_name' in scene2['4'].attrs
        assert scene2['4'].attrs['standard_name'] == 'backscatter'

    def test_aggregate_with_boundary(self):
        """Test aggregation with boundary argument."""
        x_size = 3711
        y_size = 3711

        scene1 = self._create_test_data(x_size, y_size)

        with pytest.raises(ValueError):
            scene1.aggregate(func='sum', x=2, y=2, boundary='exact')

        scene2 = scene1.aggregate(func='sum', x=2, y=2, boundary='trim')
        expected_aggregated_shape = (y_size // 2, x_size // 2)
        self._check_aggregation_results(expected_aggregated_shape, scene1, scene2, x_size, y_size)
