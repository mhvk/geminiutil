
import os
import yaml

from ..base import Base, FITSFile, Instrument, ObservationType, ObservationClass, ObservationBlock, Object

from .. import base

from sqlalchemy import Column, ForeignKey

from sqlalchemy.orm import relationship, backref, object_session
from sqlalchemy import func

from astropy.utils import misc
from astropy import units
detector_yaml_fname = os.path.join(os.path.dirname(__file__), 'data', 'gmos_detector_information.yml')
detector_information = yaml.load(file(detector_yaml_fname))

#sqlalchemy types
from sqlalchemy import String, Integer, Float, DateTime, Boolean

class GMOSMask(Base):
    __tablename__ = 'gmos_mask'

    id = Column(Integer, ForeignKey('fits_file.id'), primary_key=True)
    name = Column(String)
    program_id = Column(Integer, ForeignKey('program.id'))

    fits = relationship(base.FITSFile)

    @misc.lazyproperty
    def table(self):
        return self.fits.data

    @classmethod
    def from_fits_object(cls, fits_object):
        session = object_session(fits_object)
        mask_name = fits_object.header['DATALAB'].lower().strip()
        mask_program = session.query(base.Program).filter_by(name=fits_object.header['GEMPRGID'].lower().strip()).one()
        mask_object = cls(mask_name, mask_program.id)
        mask_object.id = fits_object.id
        return mask_object



    def __init__(self, name, program_id):
        self.name = name
        self.program_id = program_id

class GMOSDetector(Base):
    __tablename__ = 'gmos_detector'

    """
    Detector properties table
    """

    id = Column(Integer, primary_key=True)
    naxis1 = Column(Integer)
    naxis2 = Column(Integer)
    ccd_name = Column(String)
    readout_direction = Column(String)
    gain = Column(Float)
    readout_noise = Column(Float)
    x_binning = Column(Integer)
    y_binning = Column(Integer)
    frame_id = Column(Integer)

    @classmethod
    def from_fits_object(cls, fits_object, ccd_no):
        hdu = fits_object.fits_data[ccd_no]

        header = hdu.header
        session = object_session(fits_object)

        x_binning, y_binning = map(int, header['CCDSUM'].split())

        readout_direction = header['ampname'].split(',')[1].strip()
        detector_object = session.query(cls).filter(cls.naxis1==header['NAXIS1'], cls.naxis2==header['NAXIS2'],
                                  cls.ccd_name==header['CCDNAME'], cls.readout_direction==readout_direction,
                                  (func.abs(cls.gain - header['GAIN']) / header['GAIN']) < 0.0001,
                                  (func.abs(cls.readout_noise - header['RDNOISE']) / header['RDNOISE']) < 0.0001,
                                  cls.x_binning==x_binning, cls.y_binning==y_binning,
                                  cls.frame_id==int(header['FRAMEID'])).all()
        if detector_object == []:
            detector_object = cls(header['NAXIS1'], header['NAXIS2'], header['CCDNAME'], readout_direction, header['GAIN'],
                       header['RDNOISE'], x_binning, y_binning, header['FRAMEID'])
            session.add(detector_object)
            session.commit()
            return detector_object
        elif len(detector_object) == 1:
            return detector_object[0]
        else:
            raise ValueError('Found more than one detectors')

    def __init__(self, naxis1, naxis2, ccd_name, readout_direction, gain, read_noise, x_binning, y_binning, frame_id):
        self.naxis1 = naxis1
        self.naxis2 = naxis2
        self.ccd_name = ccd_name
        self.readout_direction = readout_direction
        self.gain = gain
        self.readout_noise = read_noise
        self.x_binning = x_binning
        self.y_binning = y_binning
        self.frame_id = frame_id

    @misc.lazyproperty
    def pixel_scale(self):
        if self.ccd_name.startswith('EEV'):
            return detector_information['pixel_scale']['eev'] * units.Unit('arcsec/pixel')
        else:
            raise NotImplemented('CCD %s not implemented yet' % self.ccd_name)

    @misc.lazyproperty
    def spectral_cutoff(self):
        if self.ccd_name.startswith('EEV'):
            return detector_information['spectral_cutoff']['eev'] * units.Unit('nm')
        else:
            raise NotImplemented('CCD %s not implemented yet' % self.ccd_name)

    def __repr__(self):
        return "<detector id=%d ccdname=%s xbin=%d ybin=%d gain=%.2f>" % (self.id, self.ccd_name, self.x_binning,
        self.y_binning, self.gain)

class GMOSMOSInstrumentSetup(Base):
    __tablename__ = 'gmos_mos_instrument_setup'

    id = Column(Integer, primary_key=True)

    filter1_id = Column(Integer, ForeignKey('gmos_filters.id'))
    filter2_id = Column(Integer, ForeignKey('gmos_filters.id'))

    grating_id = Column(Integer, ForeignKey('gmos_gratings.id'))

    grating_slit_wavelength_value = Column(Float)
    grating_slit_wavelength_unit = units.Unit('nm')

    grating_central_wavelength_value = Column(Float)
    grating_central_wavelength_unit = units.Unit('nm')

    grating_tilt_value = Column(Float)
    grating_tilt_unit = units.Unit('degree')

    grating_order = Column(Integer)

    detector1_id = Column(Integer, ForeignKey('gmos_detector.id'))
    detector2_id = Column(Integer, ForeignKey('gmos_detector.id'))
    detector3_id = Column(Integer, ForeignKey('gmos_detector.id'))

    filter1 = relationship(GMOSFilter, primaryjoin=(GMOSFilter.id==detector1_id),
                                uselist=False)

    filter2 = relationship(GMOSFilter, primaryjoin=(GMOSFilter.id==detector1_id),
                                uselist=False)



    detector1 = relationship(GMOSDetector, primaryjoin=(GMOSDetector.id==detector1_id),
                                uselist=False)

    detector2 = relationship(GMOSDetector, primaryjoin=(GMOSDetector.id==detector2_id),
                                uselist=False)

    detector3 = relationship(GMOSDetector, primaryjoin=(GMOSDetector.id==detector3_id),
                                uselist=False)


    @classmethod
    def from_fits_object(cls, fits_object):
        session = object_session(fits_object)
        header = fits_object.fits_data[0].header

        filter1_id = session.query(GMOSFilter).filter_by(name=header['filter1']).one().id
        filter2_id = session.query(GMOSFilter).filter_by(name=header['filter2']).one().id

        grating_id = session.query(GMOSGrating).filter_by(name=header['grating']).one().id

        grating_central_wavelength = header['centwave']
        grating_slit_wavelength = header['grwlen']

        grating_tilt = header['grtilt']
        grating_order = header['grorder']

        detector1_id = GMOSDetector.from_fits_object(fits_object, 1).id
        detector2_id = GMOSDetector.from_fits_object(fits_object, 2).id
        detector3_id = GMOSDetector.from_fits_object(fits_object, 3).id


        instrument_setup_object = session.query(cls).filter(cls.filter1_id==filter1_id, cls.filter2_id==filter2_id,
            cls.grating_id==grating_id,
            (func.abs(cls.grating_central_wavelength_value - grating_central_wavelength)
                                                    / grating_central_wavelength) < 0.0001,
            (func.abs(cls.grating_slit_wavelength_value - grating_slit_wavelength)
                                                    / grating_slit_wavelength) < 0.0001,
            (func.abs(cls.grating_tilt_value - grating_tilt)
                                                    / grating_tilt) < 0.0001,
            cls.detector1_id==detector1_id, cls.detector2_id==detector2_id, cls.detector3_id==detector3_id).all()

        if instrument_setup_object == []:
            instrument_setup_object = cls(filter1_id, filter2_id, grating_id, grating_central_wavelength, grating_tilt,
                                            grating_order, detector1_id, detector2_id, detector3_id)
            session.add(instrument_setup_object)
            session.commit()

        elif len(instrument_setup_object) == 1:
            return instrument_setup_object

        else:
            raise ValueError('More than one Instrument setup with the same setup found: %s' % instrument_setup_object)




    def __init__(self, filter1_id, filter2_id, grating_id, grating_central_wavelength_value, grating_tilt_value,
                 grating_order, detector1_id, detector2_id, detector3_id):
        self.filter1_id = filter1_id
        self.filter2_id = filter2_id
        self.grating_id = grating_id
        self.grating_central_wavelength_value = grating_central_wavelength_value
        self.grating_tilt_value = grating_tilt_value
        self.grating_order = grating_order
        self.detector1_id = detector1_id
        self.detector2_id = detector2_id
        self.detector3_id = detector3_id





class GMOSFilter(Base):
    __tablename__ = 'gmos_filters'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    fname = Column(String)
    path = Column(String)
    wavelength_start_value = Column(Float)
    wavelength_start_unit = Column(String)

    wavelength_end_value = Column(Float)
    wavelength_end_unit = Column(String)


    @property
    def full_path(self):
        return self.path.join(self.path, self.fname)

    @property
    def wavelength_start(self):
        return units.Quantity(self.wavelength_start_value, self.wavelength_start_unit)

    @property
    def wavelength_end(self):
        return units.Quantity(self.wavelength_end_value, self.wavelength_end_unit)


    def __repr__(self):
        return "<GMOS Filter %s>" % self.name

class GMOSGrating(Base):
    __tablename__ = 'gmos_gratings'

    id = Column(Integer, primary_key=True)

    name = Column(String)

    ruling_density_value = Column(Float)
    ruling_density_unit = units.Unit('1/mm') # lines/mm

    blaze_wavelength_value = Column(Float)
    blaze_wavelength_unit = units.Unit('nm')

    R = Column(Float)

    coverage_value = Column(Float)
    coverage_unit = units.Unit('nm')

    wavelength_start_value = Column(Float)
    wavelength_start_unit = units.Unit('nm')

    wavelength_end_value = Column(Float)
    wavelength_end_unit = units.Unit('nm')

    wavelength_offset_value = Column(Float)
    wavelength_offset_unit = units.Unit('nm')

    y_offset_value = Column(Float)
    y_offset_unit = units.Unit('nm')


    def __getattr__(self, item):
        if item in ['ruling_density', 'blaze_wavelength', 'coverage', 'wavelength_start', 'wavelength_end',
                    'wavelength_offset', 'y_offset']:
            item_value = getattr(self, '%s_value' % item)
            item_unit = getattr(self, '%s_unit' % item)
            return units.Quantity(item_value, item_unit)
        else:
            raise AttributeError('%s has no attribute %s' % (self.__class__.__name__, item))

    def __repr__(self):
        return "<GMOS Grating %s>" % self.name



class GMOSMOSRawFITS(Base):
    __tablename__ = 'gmos_mos_raw_fits'


    id = Column(Integer, ForeignKey('fits_file.id'), primary_key=True)
    date_obs = Column(DateTime)
    instrument_id = Column(Integer, ForeignKey('instrument.id'))
    observation_block_id = Column(Integer, ForeignKey('observation_block.id'))
    observation_class_id = Column(Integer, ForeignKey('observation_class.id'))
    observation_type_id = Column(Integer, ForeignKey('observation_type.id'))
    object_id = Column(Integer, ForeignKey('object.id'))
    mask_id = Column(Integer, ForeignKey('gmos_mask.id'))


    instrument_setup_id = Column(Integer, ForeignKey('gmos_mos_instrument_setup.id'))

    exclude = Column(Boolean)


    fits = relationship(FITSFile, uselist=False, backref='raw_fits')
    instrument = relationship(Instrument, uselist=False, backref='raw_fits')
    observation_block = relationship(ObservationBlock, uselist=False, backref='raw_fits')
    observation_class = relationship(ObservationClass, uselist=False, backref='raw_fits')
    observation_type = relationship(ObservationType, uselist=False, backref='raw_fits')
    object = relationship(base.Object, uselist=False, backref='raw_fits')
    mask = relationship(GMOSMask, uselist=False, backref='raw_fits')

    instrument_setup = relationship(GMOSMOSInstrumentSetup)

    def __init__(self, date_obs, instrument_id, observation_block_id, observation_class_id, observation_type_id,
                 object_id, mask_id=None, chip1_detector_id=None, chip2_detector_id=None, chip3_detector_id=None, exclude=False):
        self.date_obs = date_obs
        self.instrument_id = instrument_id
        self.observation_block_id = observation_block_id
        self.observation_class_id = observation_class_id
        self.observation_type_id = observation_type_id
        self.exclude = exclude

        self.mask_id = mask_id
        self.object_id = object_id
        self.detector1_id = chip1_detector_id
        self.detector2_id = chip2_detector_id
        self.detector3_id = chip3_detector_id

    def __repr__(self):
        return '<gmos fits="%s" class="%s" type="%s" object="%s">' % (self.fits.fname, self.observation_class.name,
                                                                  self.observation_type.name, self.object.name)