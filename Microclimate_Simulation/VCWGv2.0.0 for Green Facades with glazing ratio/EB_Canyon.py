import numpy
import os
import math
from scipy.optimize import fsolve
from Read_Input import Data_Site
from scipy.interpolate import interp1d
from psychrometrics import psychrometrics
from Simparam import SimParam
from weather import Weather
from UrbanSurfaceHeatFlux import Surface_HeatFlux
from Radiation_Functions import RadiationFunctions
from Resistance_Functions import Ressitance_Calculations
from scipy.optimize import least_squares
import copy

"""
Compute energy balance at the surfaces in the canyon
Developed by Mohsen Moradi and Amir A. Aliabadi
Atmospheric Innovations Research (AIR) Laboratory, University of Guelph, Guelph, Canada
Last update: May 2021
"""

class EnergyBalanceCanyon_Def():

    def __init__(self,CiCO2LeafTreeSun_init,CiCO2LeafTreeShd_init,CiCO2LeafGroundVegSun_init,CiCO2LeafGroundVegShd_init,
                 CiCO2LeafWallVegSun_init,CiCO2LeafWallVegShd_init,Tdp_gimp_init,Tdp_gbare_init,Tdp_gveg_init,Ttree_init):

        class Src_Def():
            pass
        self.Src = Src_Def()
        self.Src.thb = None
        self.Src.qhb = None
        self.Src.tvb = None

        class Gflux_Def():
            pass
        self.Gflux = Gflux_Def()
        self.Gflux.GfluxGroundImp = 0
        self.Gflux.GfluxGroundBare = 0
        self.Gflux.GfluxGroundVeg = 0
        self.Gflux.GfluxGround = 0
        self.Gflux.CfluxWallVeg = 0

        class WallBehindFoliage_Def():
            SWRabsSun = 0.0
            SWRabsShade = 0.0
            LWRabsSun = 0.0
            LWRabsShade = 0.0
            SWRabsVeg = 0.0
            LWRabsVeg = 0.0
        self.WallBehindFoliage = WallBehindFoliage_Def()
        self.Gflux.CfluxWallImp = 0

        class Hflux_Def():
            pass
        self.Hflux = Hflux_Def()
        self.Hflux.HfluxGroundImp = 0
        self.Hflux.HfluxGroundBare = 0
        self.Hflux.HfluxGroundVeg = 0
        self.Hflux.HfluxWallVeg = 0
        self.Hflux.HfluxWallImp = 0
        self.Hflux.HfluxTree = 0
        self.Hflux.HfluxGround = 0
        self.Hflux.HfluxCanyon = 0

        class LEflux_Def():
            pass
        self.LEflux = LEflux_Def()
        self.LEflux.LEfluxGroundImp = 0
        self.LEflux.LEfluxGroundBare = 0
        self.LEflux.LEfluxGroundBarePond = 0
        self.LEflux.LEfluxGroundBareSoil = 0
        self.LEflux.LEfluxGroundVeg = 0
        self.LEflux.LEfluxGroundVegInt = 0
        self.LEflux.LEfluxGroundVegPond = 0
        self.LEflux.LEfluxGroundVegSoil = 0
        self.LEflux.LTEfluxGroundVeg = 0
        self.LEflux.LEfluxGround = 0
        self.LEflux.LEfluxWallVeg = 0
        self.LEflux.LEfluxTreeInt = 0
        self.LEflux.LTEfluxTree = 0
        self.LEflux.LEfluxTree = 0
        self.LEflux.LEfluxCanyon = 0

        class Eflux_Def():
            pass
        self.Eflux = Eflux_Def()
        self.Eflux.EfluxGroundImp = 0
        self.Eflux.EfluxGroundBarePond = 0
        self.Eflux.EfluxGroundBareSoil = 0
        self.Eflux.EfluxGroundBare = 0
        self.Eflux.EfluxGroundVegInt = 0
        self.Eflux.EfluxGroundVegPond = 0
        self.Eflux.EfluxGroundVegSoil = 0
        self.Eflux.TEfluxGroundVeg = 0
        self.Eflux.EfluxGroundVeg = 0
        self.Eflux.EfluxTreeInt = 0
        self.Eflux.TEfluxTree = 0
        self.Eflux.EfluxGround = 0
        self.Eflux.EfluxTree = 0
        self.Eflux.EfluxWallVeg = 0
        self.Eflux.Eflux_canyon = 0

        class Tdepth_Def():
            pass
        self.Tdepth = Tdepth_Def()
        self.Tdepth.TDampGroundImp = Tdp_gimp_init
        self.Tdepth.TDampGroundBare = Tdp_gbare_init
        self.Tdepth.TDampGroundVeg = Tdp_gveg_init

        self.Ttree = [Ttree_init]

        class SWR_Def():
            pass
        self.SWR = SWR_Def()
        self.SWR.SWRin = None
        self.SWR.SWRout = None
        self.SWR.SWRabs = None
        self.SWR.SWRabsDir = None
        self.SWR.SWRabsDiff = None
        self.SWR.SWREB = None
        self.SWR.SWRabsTotalUrban = None
        self.SWR.SWRinTotalUrban = None
        self.SWR.SWRoutTotalUrban = None
        self.SWR.SWREBTotalUrban = None

        class LWR_Def():
            pass
        self.LWR = LWR_Def()
        self.LWR.LWRin = 0
        self.LWR.LWRout = 0
        self.LWR.LWRabs = 0
        self.LWR.LWREB = 0
        self.LWR.LWRabsTotalUrban = 0
        self.LWR.LWRinTotalUrban = 0
        self.LWR.LWRoutTotalUrban = 0
        self.LWR.LWREBTotalUrban = 0

        class CiCO2_Def():
            pass
        self.CiCO2 = CiCO2_Def()
        self.CiCO2.CiCO2LeafTreeSun = CiCO2LeafTreeSun_init
        self.CiCO2.CiCO2LeafTreeShd = CiCO2LeafTreeShd_init
        self.CiCO2.CiCO2LeafGroundVegSun = CiCO2LeafGroundVegSun_init
        self.CiCO2.CiCO2LeafGroundVegShd = CiCO2LeafGroundVegShd_init
        self.CiCO2.CiCO2LeafWallVegSun = CiCO2LeafWallVegSun_init
        self.CiCO2.CiCO2LeafWallVegShd = CiCO2LeafWallVegShd_init

        class Res_Def():
            pass
        self.Res = Res_Def()
        self.Res.rap_can = 0
        self.Res.rap_Htree_In = 0
        self.Res.rap_WallVeg = 0
        self.Res.rb_HGround = 0
        self.Res.rb_LGround = 0
        self.Res.r_soilGroundbare = 0
        self.Res.r_soilGroundveg = 0
        self.Res.rs_sunGround = 0
        self.Res.rs_shdGround = 0
        self.Res.rs_sunTree = 0
        self.Res.rs_shdTree = 0
        self.Res.rs_WallImp = 0
        self.Res.rs_WallVeg = 0

        class OtherParam_Def():
            pass
        self.OtherParam = OtherParam_Def()
        self.OtherParam.Ri_nearGround = 0
        self.OtherParam.Utotal_nearGround = 0
        self.OtherParam.T_nearGround = 0
        self.OtherParam.Tground = 0
        self.OtherParam.alp_soil_bare = 0
        self.OtherParam.alp_soil_veg = 0
        self.OtherParam.Fsun_L = 0
        self.OtherParam.Fshd_L = 0
        self.OtherParam.dw_L = 0


    def EBSolver_Canyon(self,TemperatureC,TempVec,MeteoData,Int,ExWater,Vwater,Owater,SoilPotW,ViewFactor,Geometry_m,ParTree,
                        geometry,FractionsGround,FractionsWall,ParSoilGround,ParInterceptionTree,PropOpticalGround,PropOpticalWall,
                        PropOpticalTree,ParThermalGround,ParVegGround,ParVegTree,SunPosition,Anthropogenic,
                        ParCalculation,VerticalProfUrban,ColParam,VCWG_param_file_path):
        """
        ------
        INPUT:
        TemperatureC: Temperature of the exterior surfaces [K]
        TempVec: Temperature of the exterior surfaces from two steps back [K]
        MeteoData: Forcing variables
        Int: Water interception [mm]
        ExWater: Extractable water [mm m^2 m^-2 ground s^-1]
        Vwater: [mm]
        Owater: Water Content [-]
        SoilPotW: [MPa]
        ViewFactor: View factors
        Geometry_m: Geometric parameters
        ParTree: Trees parameter
        geometry: Normalized geometric parameters
        FractionsGround: Fractions of ground covered by vegetation, impervious, and bare surface
        ParSoilGround: Soil parameters
        ParInterceptionTree: specific water retained by the tree [mm m^2 VEG area m^-2 plant area]
        PropOpticalGround: Optical properties of the ground (albedo and emissivity)
        PropOpticalWall: Optical properties of the wall (albedo and emissivity)
        PropOpticalTree: Optical properties of the tree (albedo and emissivity)
        ParThermalGround: Thermal properties of the ground (Thermal conductivity[W m^-1 K^-1], Volumetric heat capacity [J m^-3 K^-1])
        ParVegGround: Ground vegetation parameters
        ParVegTree: Trees parameter
        SunPosition: sun angles
        Anthropogenic: Anthropogenic heat
        ParCalculation: General calculation parameters
        VerticalProfUrban: Vertical profile of variables obtained from 1-D model
        ColParam: 1-D model parameters
        -------
        OUTPUT:
        Src: Sink/source terms in column model
             thb: Kinematic sensible heat flux from ground [K m s^-1]
             tvb: Kinematic sensible heat flux from wall [K m s^-1]
             qhb: Evaporative flux [kg kg^-1 m s^-1]
        Gflux: Ground (Conductive) heat fluxes
               GfluxGroundImp: Ground heat flux from impervious surface [W m^-2]
               GfluxGroundBare: Ground heat flux from bare surface [W m^-2]
               GfluxGroundVeg: Ground heat flux from vegetated surface [W m^-2]
               GfluxGround: Total ground heat flux [W m^-2]
               CfluxWallVeg: Conductive heat flux from vegetated wall [W m^-2]
               CfluxWallImp: Conductive heat flux from impervious wall [W m^-2]
        Hflux: Sensible heat fluxes
               HfluxGroundImp: Sensible heat flux from impervious surface [W m^-2]
               HfluxGroundBare: Sensible heat flux from bare surface [W m^-2]
               HfluxGroundVeg: Sensible heat flux from vegetated surface [W m^-2]
               HfluxWallVeg: Sensible heat flux from vegetated wall [W m^-2]
               HfluxWallImp: Sensible heat flux from impervious wall [W m^-2]
               HfluxTree: Sensible heat flux from tree [W m^-2]
               HfluxGround: Total sensible heat flux from ground [W m^-2]
               HfluxCanyon: Total sensible heat flux in the canyon [W m^-2]
        LEflux: Latent heat fluxes
                LEfluxGroundImp: Latent heat flux from impervious surface [W m^-2]
                LEfluxGroundBare: Total latent heat flux from bare ground [W m^-2]
                LEfluxGroundBarePond: Latent heat flux from bare surface [W m^-2]
                LEfluxGroundBareSoil: Latent heat flux from soil under bare surface [W m^-2]
                LEfluxGroundVeg: Total latent heat flux from vegetated ground [W m^-2]
                LEfluxGroundVegInt: Latent heat flux from intercepted water on the low vegetation [W m^-2]
                LEfluxGroundVegPond: Latent heat flux from surface under low vegetation [W m^-2]
                LEfluxGroundVegSoil: Latent heat flux from soil under vegetated surface [W m^-2]
                LTEfluxGroundVeg: Latent heat flux from transpiration of low vegetation [W m^-2]
                LEfluxGround: Total latent heat flux from ground [W m^-2]
                LEfluxWallVeg: Latent heat flux from vegetated wall [W m^-2]
                LEfluxTreeInt: Latent heat flux from intercepted water on trees [W m^-2]
                LTEfluxTree: Latent heat flux from transpiration of trees [W m^-2]
                LEfluxTree: Total latent heat flux from trees [W m^-2]
                LEfluxCanyon: Total latent heat flux in the canyon [W m^-2]
        Eflux: Evaporative fluxes
               EfluxGroundImp: Evaporation from intercepted water on impervious surface [kg m^-2 s^-1]
               EfluxGroundBarePond: Evaporation from intercepted water on bare ground [kg m^-2 s^-1]
               EfluxGroundBareSoil: Evaporation from soil under bare ground [kg m^-2 s^-1]
               EfluxGroundBare: Total evaporative flux from bare ground [kg m^-2 s^-1]
               EfluxGroundVegInt: Evaporation from intercepted water on low vegetation [kg m^-2 s^-1]
               EfluxGroundVegPond: Evaporation from intercepted water on ground under vegetation [kg m^-2 s^-1]
               EfluxGroundVegSoil: Evaporation from soil under vegetated ground [kg m^-2 s^-1]
               TEfluxGroundVeg: Transpiration from low vegetation [kg m^-2 s^-1]
               EfluxGroundVeg: Total evaporative flux from vegetated ground [kg m^-2 s^-1]
               EfluxTreeInt: Evaporation from intercepted water on trees [kg m^-2 s^-1]
               TEfluxTree: Transpiration from trees [kg m^-2 s^-1]
               EfluxGround: Total evaporative flux from ground [kg m^-2 s^-1]
               EfluxTree: Total evaporative flux from tree [kg m^-2 s^-1]
               EfluxWallVeg: Total evaporative flux from vegetated wall [kg m^-2 s^-1]
        Tdepth: Deep soil temperature
                TDampGroundImp: Deep soil temperature of impervious ground [K]
                TDampGroundBare: Deep soil temperature of bare ground [K]
                TDampGroundVeg: Deep soil temperature of vegetated ground [K]
        SWR: Shortwave radiations
             SWRin: Incoming shortwave radiation [W m^-2]
             SWRout: Outgoing shortwave radiation [W m^-2]
             SWRabs: Net shortwave radiation [W m^-2]
             SWRabsDir: Absorbed direct shortwave radiation [W m^-2]
             SWRabsDiff: Absorbed diffuse shortwave radiation [W m^-2]
             SWREB: Energy balance for shortwave radiation [W m^-2]
             SWRabsTotalUrban: Total absorbed shortwave radiation in the urban [W m^-2]
             SWRinTotalUrban: Total incoming shortwave radiation to the urban [W m^-2]
             SWRoutTotalUrban: Total outgoing shortwave radiation from the urban [W m^-2]
             SWREBTotalUrban: Total energy balance for shortwave radiation [W m^-2]
        LWR: Longwave radiations
             LWRin: Incoming longwave radiation [W m^-2]
             LWRout: Outgoing longwave radiation [W m^-2]
             LWRabs: Net longwave radiation [W m^-2]
             LWREB: Energy balance for longwave radiation [W m^-2]
             LWRabsTotalUrban: Total absorbed longwave radiation in the urban [W m^-2]
             LWRinTotalUrban: Total incoming longwave radiation to the urban [W m^-2]
             LWRoutTotalUrban: Total outgoing longwave radiation from the urban [W m^-2]
             LWREBTotalUrban: Total energy balance for longwave radiation [W m^-2]
        CiCO2: Leaf Interior CO2 concentration
               CiCO2LeafTreeSun: Leaf Interior CO2 concentration of sunlit tree [umolCO2 mol^-1]
               CiCO2LeafTreeShd: Leaf Interior CO2 concentration shaded tree [umolCO2 mol^-1]
               CiCO2LeafGroundVegSun: Leaf Interior CO2 concentration of sunlit low vegetation [umolCO2 mol^-1]
               CiCO2LeafGroundVegShd: Leaf Interior CO2 concentration of shaded low vegetation [umolCO2 mol^-1]
               CiCO2LeafWallVegSun_init: Sunlit leaf Interior CO2 concentration of vegetated sunlit wall[umolCO2 mol^-1]
               CiCO2LeafWallVegShd_init: Shaded leaf Interior CO2 concentration of vegetated shaded wall[umolCO2 mol^-1]
        Res: Resistances
             rap_can: Aerodynamic resistance near the ground [s m^-1]
             rap_Htree_In: Aerodynamic resistance between trees and canyon air [s m^-1]
             rap_WallVeg: Aerodynamic resistance near the vegetated wall [s m^-1]
             rb_HGround: Leaf boundary layer resistance [s m^-1]
             rb_LGround: Leaf boundary layer resistance for low vegetation [s m^-1]
             r_soilGroundbare: Bare soil resistance [s m^-1]
             r_soilGroundveg: Vegetated soil resistance [s m^-1]
             rs_sunGround: Stomatal resistance of sunlit low vegetation [s m^-1]
             rs_shdGround: Stomatal resistance of shaded low vegetation [s m^-1]
             rs_sunTree: Stomatal resistance of sunlit trees [s m^-1]
             rs_shdTree: Stomatal resistance of shaded trees [s m^-1]
             rs_WallImp: Stomatal resistance of impervious wall [s m^-1]
             rs_WallVeg: Stomatal resistance of shaded vegetated wall [s m^-1]
        OtherParam: Other parameters
                    Ri_nearGround: Richardson number near ground
                    Utotal_nearGround:
                    T_nearGround:
                    Tground:
                    alp_soil_bare: Relative humidity of bare soil [0-1]
                    alp_soil_veg: Relative humidity of vegetated soil [0-1]
                    Fsun_L: Fraction of sunlit for low vegetation [-]
                    Fshd_L: Fraction of shaded for low vegetation [-]
                    dw_L: Fraction of ground vegetation covered by intercepted water [-]
        """

        RadiationCal = RadiationFunctions()
        SurfaceHeatFlux = Surface_HeatFlux()

        Geometry_m, ParTree, geometry, FractionsRoof, FractionsWall, FractionsGround, WallLayers, ParSoilRoof, \
        ParSoilGround, ParInterceptionTree, PropOpticalRoof, PropOpticalGround, PropOpticalWall, \
        PropOpticalTree, ParThermalRoof, ParThermalGround, ParThermalWall,ParVegRoof,\
        ParVegGround,ParVegTree,Person,ColParam,RSMParam,TimeParam,ViewFactorCal_Param,bld,zone,\
        charLength,BEMParam = Data_Site(VCWG_param_file_path)

        # Shortwave radiation
        SWRin_t, SWRout_t, SWRabs_t, SWRabsDir_t, SWRabsDiff_t, SWREB_t = \
        RadiationCal.TotalSWRabsorbed(geometry, FractionsGround, ParTree, PropOpticalGround, PropOpticalWall,
                                      PropOpticalTree, ParVegTree, MeteoData, SunPosition, ViewFactor)

        # Longwave radiation 
        LWRin_t, LWRout_t, LWRabs_t, LWREB_t = \
            RadiationCal.TotalLWRabsorbed(TemperatureC, geometry, MeteoData, FractionsGround, PropOpticalGround,
                                        PropOpticalWall, PropOpticalTree, ParTree, ViewFactor)

        # Calculate deep soil temperature
        # Option 1: Using force-restore method
        if ParThermalGround.Tdeep_ctrl == 'Force_Restore':
            # Impervious ground
            _G1GroundImp_, Tdp_ground_imp = \
                SurfaceHeatFlux.ForceRestore_Conductive_Heat_Imp(TemperatureC,self.Tdepth,TempVec,ParCalculation,ParThermalGround,FractionsGround)
            # Bare ground
            type = 0
            _G1GroundBare_, Tdp_ground_bare = \
                SurfaceHeatFlux.ForceRestore_Conductive_Heat_Soil(TemperatureC,self.Tdepth,Owater,TempVec,ParCalculation,
                                                                  ParSoilGround,ParVegGround,ParVegTree,FractionsGround,type)
            # Vegetated ground
            type = 1
            _G1GroundVeg_, Tdp_ground_veg = \
                SurfaceHeatFlux.ForceRestore_Conductive_Heat_Soil(TemperatureC,self.Tdepth,Owater,TempVec,ParCalculation,
                                                                  ParSoilGround,ParVegGround,ParVegTree,FractionsGround,type)
        # Option 2: Using climate data
        elif ParThermalGround.Tdeep_ctrl == 'Climate_Data':
            Tdp_ground_imp = copy.copy(MeteoData.TdeepSoil)
            Tdp_ground_bare = copy.copy(MeteoData.TdeepSoil)
            Tdp_ground_veg = copy.copy(MeteoData.TdeepSoil)

        # Calculate turbulent heat fluxes from ground and trees to the canyon
        HfluxGroundImp, HfluxGroundBare, HfluxGroundVeg, HfluxTree, Eground_imp_pond, Eground_bare_pond, Eground_bare_soil,\
        Eground_veg_int, Eground_veg_pond, Eground_veg_soil, TEground_veg, E_tree_int, TE_tree, Ebare, Eveg, Etree, LEfluxGroundImp,\
        LEfluxGroundBarePond, LEfluxGroundBareSoil, LEfluxGroundVegInt, LEfluxGroundVegPond, LEfluxGroundVegSoil, LTEfluxGroundVeg,\
        LEfluxTreeInt, LTEfluxTree, LEbare, LEveg, LEtree, Ci_sun_tree, Ci_shd_tree, Ci_sun_ground, Ci_shd_ground, rap_can,\
        rap_Htree_In, rb_H, rb_L, r_soil_bare, r_soil_veg, alp_soil_bare, alp_soil_veg, rs_sun_L, rs_shd_L, rs_sun_H,\
        rs_shd_H, Fsun_L, Fshd_L, dw_L = \
            SurfaceHeatFlux.HeatFlux_ground_1D(TemperatureC, MeteoData, Geometry_m, geometry, FractionsGround,ParTree,
                                               ParVegGround, ParVegTree, ParSoilGround, SoilPotW, Owater, Vwater, ExWater,
                                               Int, self.CiCO2, ParInterceptionTree, ParCalculation,SWRabsDir_t.SWRabsTree,
                                               SWRabsDiff_t.SWRabsTree, SWRabsDir_t.SWRabsGroundVeg,SWRabsDiff_t.SWRabsGroundVeg,
                                               VerticalProfUrban,ColParam)

        # Calculate turbulent heat fluxes from impervious and vegetated wall to canyon
        HfluxWallVeg, HfluxWallImp, Ewsun, Ewshade, LEwsun, LEwshade, LEwveg, rap_WallVeg, rs_WallImp, rs_WallVeg = \
            SurfaceHeatFlux.HeatFlux_wall(MeteoData, TemperatureC, Geometry_m,geometry,VerticalProfUrban,FractionsGround,ParCalculation,
                                          PropOpticalGround,PropOpticalWall,PropOpticalTree,ParVegTree,ParTree,SunPosition,ColParam,ViewFactor)

        # Calculate total sensible heat flux [W m^-2]
        HfluxWall = HfluxWallImp * FractionsWall.fimp + HfluxWallVeg * FractionsWall.fveg

        # Calculate total heat flux from ground [W m^-2]
        HfluxGround = HfluxGroundImp*FractionsGround.fimp + HfluxGroundBare*FractionsGround.fbare + HfluxGroundVeg*FractionsGround.fveg

        LEfluxGroundBare = LEfluxGroundBarePond + LEfluxGroundBareSoil
        LEfluxGroundVeg = LEfluxGroundVegInt + LEfluxGroundVegPond + LEfluxGroundVegSoil + LTEfluxGroundVeg
        LEfluxGround = LEfluxGroundImp * FractionsGround.fimp + LEfluxGroundBare * FractionsGround.fbare + LEfluxGroundVeg * FractionsGround.fveg
        LEfluxTree = LEfluxTreeInt + LTEfluxTree
        
        # Shortwave radiation
        # Absorbed shortwave radiation at the impervious wall [W m^-2]
        SWRabsWallImp = SWRabs_t.SWRabsWallImp

        # Longwave radiation
        # Total absorbed longwave radiation by impervious wall [W m^-2]
        LWRabsWallImp = LWRabs_t.LWRabsWallImp

        SWRabsWallVeg = SWRabs_t.SWRabsWallVeg
        LWRabsWallVeg = LWRabs_t.LWRabsWallVeg

        LWRabsWall = (LWRabsWallImp + LWRabsWallVeg) / 2
        # Shortwave radiation absorption
        SWRabsWall = (SWRabsWallImp + SWRabsWallVeg) / 2

        # Call the Penman-Monteith calculation function
        Tdepth_rural_init = 300.0
        CiCO2Ground_Sun_Rural_init = 400.0
        CiCO2Ground_Shade_Rural_init = 400.0

        ResistanceCal = Ressitance_Calculations()

        # soil heat flux [W m^-2]
        G_wallveg = 0
        # Height of measured wind speed [m]
        h_wind = 10
        
        # Leaf area index of vegetated wall
        LAI = 3
        # Stem area index for the wall vegetation [-]
        SAI = 0.001
        # Air density [kg m^-3]
        rho_atm = copy.copy(VerticalProfUrban.rho[Geometry_m.nz_u])
        # Specific humidity at canyon
        qcanyon = copy.copy(VerticalProfUrban.qn[0])
        # Aerodynamic resistance near the vegetated wall [s m^-1]
        rap_WallVeg = self.Res.rap_WallVeg
        # Leaf dimension of wall vegetation [cm]
        d_leaf = 0.8
        
        Hcan = Geometry_m.Height_canyon

        # Wind profile from 1-D model
        vx = copy.copy(VerticalProfUrban.vx)
        vy = copy.copy(VerticalProfUrban.vy)
        z_urban = copy.copy(Geometry_m.z[:-1])

        vx_intp = interp1d(z_urban, vx)
        vy_intp = interp1d(z_urban, vy)

        # Wind speed
        u_Hcan = numpy.sqrt(vx_intp(Hcan) ** 2 + vy_intp(Hcan) ** 2)
        # Wind speed at the top of the domain [m s^-1]
        WindSpeed_top = numpy.sqrt(VerticalProfUrban.vx[-1]**2 + VerticalProfUrban.vy[-1]**2)
        # (if they are equal, then Attenuation Coefficient will be zero)
        wind_top = WindSpeed_top if WindSpeed_top != u_Hcan else u_Hcan+0.1
        # Attenuation coefficient
        alpha = math.log(wind_top / u_Hcan) / (MeteoData.Zatm / Hcan - 1)

        Zf = Geometry_m.Height_canyon / 2

        # Wind profile from 1-D model
        vx = copy.copy(VerticalProfUrban.vx)
        vy = copy.copy(VerticalProfUrban.vy)
        z_urban = copy.copy(Geometry_m.z[:-1])

        vx_intp = interp1d(z_urban, vx)
        vy_intp = interp1d(z_urban, vy)

        # Wind speed
        u_Lveg = numpy.sqrt(vx_intp(Zf) ** 2 + vy_intp(Zf) ** 2)

        # Calculate fraction of vegetation covered by intercepted water (Deardorff 1978)
        # Specific water retained by a vegetated surface [mm m^2 VEG area m^-2 plant area]
        Sp_In = 0.2
        # Maximum possible interception on vegetated wall [mm]
        In_max_L = Sp_In * (LAI + SAI)
        # Fraction of wall vegetation covered by intercepted water [-]
        dw_L = min(1, (Int.IntWallVeg / In_max_L)**(2/3))

        # Parameter definitions
        TwImp = TemperatureC[3]
        TwVeg = TemperatureC[4]

        Tavg_canyon = numpy.mean(VerticalProfUrban.th[0:Geometry_m.nz_u])
        
        # dry air density [kg m^-3]
        rho_atm = numpy.mean(VerticalProfUrban.rho[:Geometry_m.nz_u])

        # Wall exterior surface temperature
        Tw = TwVeg

        # Air specific heat [J kg^-1 K^-1]
        cp_atm = 1005 + (((Tavg_canyon - 273.15) + 23.15) ** 2) / 3364

        # Initial Tleaf (start with air temperature)
        Tleaf = MeteoData.Tatm

        # Constants
        rl = 100  # Leaf boundary resistance [s m^-1]
        R = 287  # Gas constant for dry air [J kg^-1 K^-1]
        
        # the transmissivity of radiation through the plant layer
        tau = 0.22

        U_leaf = max(0.1, float(numpy.mean(numpy.sqrt(
            numpy.asarray(VerticalProfUrban.vx[:Geometry_m.nz_u], dtype=float) ** 2 +
            numpy.asarray(VerticalProfUrban.vy[:Geometry_m.nz_u], dtype=float) ** 2))))
        b = max(1e-6, 0.01 * (U_leaf + 0.3))

        rad = RadiationFunctions()

        # Longwave radiation absorption
        LWRin_t, LWRout_t, LWRabs, LWREB_t = rad.TotalLWRabsorbed(TemperatureC, geometry, MeteoData, FractionsGround, PropOpticalGround,
                                          PropOpticalWall, PropOpticalTree, ParTree, ViewFactor)
    
        # Shortwave radiation absorption
        SWRin_t, SWRout_t, SWRabs, SWRabsDir_t, SWRabsDiff_t, SWREB_t = rad.TotalSWRabsorbed(geometry, FractionsGround, ParTree, PropOpticalGround, PropOpticalWall,
                                          PropOpticalTree, ParVegTree, MeteoData, SunPosition, ViewFactor)

        LWRabsVeg = (1 - tau) * LWRabs.LWRabsWallVeg
        SWRabsVeg = (1 - tau) * SWRabs.SWRabsWallVeg

        # Latent heat vaporization/condensation [J kg^-1]
        L_heat = 1000 * (2501.3 - 2.361 * (Tavg_canyon - 273.15))
                
        # Iterate to balance energy (stabilized update using numeric derivative)
        max_iter = 50
        Tleaf = MeteoData.Tatm
        is_daytime = SWRabsVeg > 0
        rl_day = 100
        rl_night = 5000
        rl_local = rl_day if is_daytime else rl_night
        rs_leaf = rl_local / (0.5 * max(LAI, 1e-3))
        G_wallveg = 0
        Tdptm1 = (TemperatureC[3] + TemperatureC[4]) / 2.0
        
        for iter in range(max_iter):
            Taf = tau * MeteoData.Tatm + (1 - tau) * (0.3 * MeteoData.Tatm + 0.6 * Tleaf + 0.1 * Tdptm1)
            rho_af = MeteoData.Pre / (R * max(Taf, 200.0))

            H_leaf = 1.1 * LAI * rho_af * cp_atm * (Tleaf - Taf) * b

            Tleaf_C = Tleaf - 273.15
            esat_Tleaf = 611.0 * numpy.exp(17.27 * Tleaf_C / (237.3 + Tleaf_C))
            esat_Taf = 611.0 * numpy.exp(17.27 * (Taf - 273.15) / (237.3 + (Taf - 273.15)))
            
            q_leaf_sat = 0.622 * esat_Tleaf / (MeteoData.Pre - 0.378 * esat_Tleaf)  # leaf surface saturated [kg/kg]
            grad_q = (q_leaf_sat - VerticalProfUrban.qn[0]) / 0.1  # [kg kg^-1 m^-1]
            grad_T = (Tleaf - Taf) / 0.1  # [K m^-1]
            D = 2.5e-5  # [m^2 s^-1]
            diff_term = -(2000.0 - cp_atm) * rho_atm * D * grad_q * grad_T * 0.1  # [W m^-2]
            H_leaf_adjusted = H_leaf + diff_term

            gamma = (cp_atm * MeteoData.Pre) / (0.622 * L_heat)
            e_air = (qcanyon * MeteoData.Pre) / (0.622 + 0.378 * qcanyon)
            LEfluxWallVeg = (rho_atm * cp_atm / gamma) * (esat_Tleaf - e_air) / (rap_WallVeg + rs_leaf)
            LEfluxWallVeg = max(0.0, float(LEfluxWallVeg)) if numpy.isfinite(LEfluxWallVeg) else 0.0

            epsilon_wall = 0.85
            sigma = 5.67e-8
            epsilon_leaf = 0.96
            XR = (1 - tau) * epsilon_leaf * epsilon_wall / (epsilon_leaf + epsilon_wall - epsilon_leaf * epsilon_wall) * sigma * (Tdptm1 ** 4 - Tleaf ** 4)

            LWRabsVeg_T = LWRabsVeg + (1 - tau) * epsilon_leaf * sigma * (Tdptm1 ** 4 - Tleaf ** 4)
            error = SWRabsVeg + LWRabsVeg_T + XR - H_leaf_adjusted - LEfluxWallVeg - G_wallveg

            if abs(error) < 0.5:
                break

            dFlux_dT = 1.1 * LAI * rho_af * cp_atm * b + (rho_atm * cp_atm / gamma) * (4098.0 * esat_Tleaf / (237.3 + Tleaf_C)**2) / (rap_WallVeg + rs_leaf) + 4 * sigma * Tleaf**3 * (1 - tau) * (epsilon_leaf + epsilon_leaf * epsilon_wall / (epsilon_leaf + epsilon_wall - epsilon_leaf * epsilon_wall))
            dT = error / max(dFlux_dT, 10.0)
            dT = max(-0.5, min(0.5, dT))
            Tleaf = max(260.0, min(350.0, Tleaf + dT))

        # Temperature between foliages
        Taf = tau * MeteoData.Tatm + (1 - tau) * (0.3 * MeteoData.Tatm + 0.6 * Tleaf + 0.1 * Tw)
        # Leaf boundary resistance
        rb_L = ResistanceCal.Leaf_BR(u_Lveg, Taf - 273.15, Tavg_canyon - 273.15, d_leaf, alpha)

        # vapor pressure saturation at vegetated wall [Pa]
        esat_veg = 611 * numpy.exp(17.27 * (Taf - 273.16) / (237.3 + (Taf - 273.16)))
        # Saturated specific humidity at vegetated wall [kg kg^-1]
        qsat_veg = numpy.round((0.622 * esat_veg) / (MeteoData.Pre - 0.378 * esat_veg),4)
        # Potential evaporation from intercepted water on vegetated wall [kg m^-2 s^-1]
        if dw_L > 1e-4:
            Eveg_int_pot = rho_atm * (qsat_veg - qcanyon) / (rb_L / ((LAI + SAI) * dw_L) + rap_WallVeg)
        else:
            Eveg_int_pot = 0.0
        # Evaporative flux from vegetated surface [W m^-2]
        EfluxWallVeg = Eveg_int_pot

        # Boolean operator for presence and absence of trees, vegetated ground, bare ground, and impervious ground
        Ctree = int(ParTree.trees == 1)
        Cveg = int(FractionsGround.fveg > 0)
        Cbare = int(FractionsGround.fbare > 0)
        Cimp = int(FractionsGround.fimp > 0)

        # Calculate total latent heat flux of canyon [W m^-2]
        LEflux_canyon = Cimp*FractionsGround.fimp*LEfluxGroundImp + Cbare*FractionsGround.fbare*(LEfluxGroundBarePond+LEfluxGroundBareSoil) + \
                        Cveg*FractionsGround.fveg*(LEfluxGroundVegInt + LEfluxGroundVegPond + LEfluxGroundVegSoil + LTEfluxGroundVeg) + \
                        Ctree*4*geometry.radius_tree*(LEfluxTreeInt + LTEfluxTree) + LEfluxWallVeg
        # Calculate total sensible heat flux of canyon [W m^-2]
        Hflux_canyon = Anthropogenic.Qf_canyon + Cimp*FractionsGround.fimp*HfluxGroundImp + Cbare*FractionsGround.fbare*HfluxGroundBare +\
                       Cveg*FractionsGround.fveg*HfluxGroundVeg + geometry.hcanyon*HfluxWall +\
                       Ctree*4*geometry.radius_tree*HfluxTree

        # Total evaporative flux from bare soil [kg m^-2 s^-1]
        EfluxGroundBare = Eground_bare_pond + Eground_bare_soil
        # Total evaporative flux from vegetated ground [kg m^-2 s^-1]
        EfluxGroundVeg = Eground_veg_int + Eground_veg_pond + Eground_veg_soil + TEground_veg
        # Total evaporative flux from ground [kg m^-2 s^-1]
        EfluxGround = Eground_imp_pond*FractionsGround.fimp + EfluxGroundBare*FractionsGround.fbare + EfluxGroundVeg*FractionsGround.fveg
        # Total evaporative flux from Canyon [kg m^-2 s^-1]
        Eflux_canyon = EfluxGround + EfluxWallVeg

        if ParTree.trees == 0:
            SWRabs_t.SWRabsTree = 0
            LWRabs_t.LWRabsTree = 0

        # Calculate trees temperature using least square method
        Ttree = self.FSolver_Tree(TempVec,TemperatureC,MeteoData,Int,ExWater,Vwater,Owater,SoilPotW,self.CiCO2,ViewFactor,Geometry_m,ParTree,
                                  geometry,FractionsGround,FractionsWall,ParSoilGround,ParInterceptionTree,PropOpticalGround,PropOpticalWall,
                                  PropOpticalTree,ParVegGround,ParVegTree,SunPosition,ParCalculation,VerticalProfUrban,ColParam)
        self.Ttree = numpy.array(Ttree)

        # Sink/source terms in temperature equation in the column model [K m s^-1]
        self.Src.thb = SurfaceHeatFlux.thb_ground
        self.Src.tvb = SurfaceHeatFlux.tvb_wall
        # Sink/source terms in humidity equation in the column model [kg kg^-1 m s^-1]
        self.Src.qhb = SurfaceHeatFlux.qhb_ground

        # Ground heat fluxes [W m^-2]
        self.Gflux.GfluxGroundImp = SWRabs_t.SWRabsGroundImp + LWRabs_t.LWRabsGroundImp - HfluxGroundImp - LEfluxGroundImp
        self.Gflux.GfluxGroundBare = SWRabs_t.SWRabsGroundBare + LWRabs_t.LWRabsGroundBare - HfluxGroundBare - (LEfluxGroundBarePond + LEfluxGroundBareSoil)
        self.Gflux.GfluxGroundVeg = SWRabs_t.SWRabsGroundVeg + LWRabs_t.LWRabsGroundVeg - HfluxGroundVeg - (LEfluxGroundVegInt + LEfluxGroundVegPond + LEfluxGroundVegSoil + LTEfluxGroundVeg)
        self.Gflux.GfluxGround = Cimp*FractionsGround.fimp*self.Gflux.GfluxGroundImp + Cveg*FractionsGround.fveg*self.Gflux.GfluxGroundVeg + Cbare*FractionsGround.fbare*self.Gflux.GfluxGroundBare
        self.WallBehindFoliage.SWRabsVeg = tau * SWRabsWallVeg
        self.WallBehindFoliage.LWRabsVeg = tau * LWRabsWallVeg - XR
        self.Gflux.CfluxWallVeg = tau * (SWRabsWallVeg + LWRabsWallVeg) - XR
        self.Gflux.CfluxWallImp = SWRabsWallImp + LWRabsWallImp - HfluxWallImp

        # Sensible heat fluxes [W m^-2]
        self.Hflux.HfluxGroundImp = HfluxGroundImp
        self.Hflux.HfluxGroundBare = HfluxGroundBare
        self.Hflux.HfluxGroundVeg = HfluxGroundVeg
        self.Hflux.HfluxWallVeg = HfluxWallVeg
        self.Hflux.HfluxWallImp = HfluxWallImp
        self.Hflux.HfluxTree = HfluxTree
        self.Hflux.HfluxGround = HfluxGround
        self.Hflux.HfluxCanyon = Hflux_canyon

        # Latent heat fluxes [W m^-2]
        self.LEflux.LEfluxGroundImp = LEfluxGroundImp
        self.LEflux.LEfluxGroundBare = LEfluxGroundBarePond + LEfluxGroundBareSoil
        self.LEflux.LEfluxGroundBarePond = LEfluxGroundBarePond
        self.LEflux.LEfluxGroundBareSoil = LEfluxGroundBareSoil
        self.LEflux.LEfluxGroundVeg = LEfluxGroundVegInt + LEfluxGroundVegPond + LEfluxGroundVegSoil + LTEfluxGroundVeg
        self.LEflux.LEfluxGroundVegInt = LEfluxGroundVegInt
        self.LEflux.LEfluxGroundVegPond = LEfluxGroundVegPond
        self.LEflux.LEfluxGroundVegSoil = LEfluxGroundVegSoil
        self.LEflux.LTEfluxGroundVeg = LTEfluxGroundVeg
        self.LEflux.LEfluxGround = LEfluxGround
        self.LEflux.LEfluxWallVeg = LEfluxWallVeg
        self.LEflux.LEfluxTreeInt = LEfluxTreeInt
        self.LEflux.LTEfluxTree = LTEfluxTree
        self.LEflux.LEfluxTree = LEfluxTree
        self.LEflux.LEfluxCanyon = LEflux_canyon

        # Evaporative fluxes [kg m^-2 s^-1]
        self.Eflux.EfluxGroundImp = Eground_imp_pond
        self.Eflux.EfluxGroundBarePond = Eground_bare_pond
        self.Eflux.EfluxGroundBareSoil = Eground_bare_soil
        self.Eflux.EfluxGroundBare = EfluxGroundBare
        self.Eflux.EfluxGroundVegInt = Eground_veg_int
        self.Eflux.EfluxGroundVegPond = Eground_veg_pond
        self.Eflux.EfluxGroundVegSoil = Eground_veg_soil
        self.Eflux.TEfluxGroundVeg = TEground_veg
        self.Eflux.EfluxGroundVeg = EfluxGroundVeg
        self.Eflux.EfluxTreeInt = E_tree_int
        self.Eflux.TEfluxTree = TE_tree
        self.Eflux.EfluxGround = EfluxGround
        self.Eflux.EfluxTree = E_tree_int+TE_tree
        self.Eflux.EfluxWallVeg = EfluxWallVeg
        self.Eflux.Eflux_canyon = Eflux_canyon

        # Deep soil temperature [K]
        self.Tdepth.TDampGroundImp = Tdp_ground_imp
        self.Tdepth.TDampGroundBare = Tdp_ground_bare
        self.Tdepth.TDampGroundVeg = Tdp_ground_veg

        # Radiation [W m^-2]
        self.SWR.SWRin = SWRin_t
        self.SWR.SWRout = SWRout_t
        self.SWR.SWRabs = SWRabs_t
        self.SWR.SWRabsDir = SWRabsDir_t
        self.SWR.SWRabsDiff = SWRabsDiff_t
        self.SWR.SWREB = SWREB_t
        self.LWR.LWRin = LWRin_t
        self.LWR.LWRout = LWRout_t
        self.LWR.LWRabs = LWRabs_t
        self.LWR.LWREB = LWREB_t

        # Leaf Interior  CO2 concentration [umolCO2 mol^-1]
        self.CiCO2.CiCO2LeafTreeSun = Ci_sun_tree
        self.CiCO2.CiCO2LeafTreeShd = Ci_shd_tree
        self.CiCO2.CiCO2LeafGroundVegSun = Ci_sun_ground
        self.CiCO2.CiCO2LeafGroundVegShd = Ci_shd_ground

        # Resistances
        self.Res.rap_can = rap_can
        self.Res.rap_Htree_In = rap_Htree_In
        self.Res.rap_WallVeg = rap_WallVeg
        self.Res.rb_HGround = rb_H
        self.Res.rb_LGround = rb_L
        self.Res.r_soilGroundbare = r_soil_bare
        self.Res.r_soilGroundveg = r_soil_veg
        self.Res.rs_sunGround = rs_sun_L
        self.Res.rs_shdGround = rs_shd_L
        self.Res.rs_sunTree = rs_sun_H
        self.Res.rs_shdTree = rs_shd_H
        self.Res.rs_WallImp = rs_WallImp
        self.Res.rs_WallVeg = rs_WallVeg

        # Other parameters
        self.OtherParam.Ri_nearGround = SurfaceHeatFlux.HfGruond_otherparam.Ri_nearGround
        self.OtherParam.Utotal_nearGround = SurfaceHeatFlux.HfGruond_otherparam.Utotal_nearGround
        self.OtherParam.T_nearGround = SurfaceHeatFlux.HfGruond_otherparam.T_nearGround
        self.OtherParam.Tground = SurfaceHeatFlux.HfGruond_otherparam.Tground
        self.OtherParam.alp_soil_bare = alp_soil_bare
        self.OtherParam.alp_soil_veg = alp_soil_veg
        self.OtherParam.Fsun_L = Fsun_L
        self.OtherParam.Fshd_L = Fshd_L
        self.OtherParam.dw_L = dw_L

    def EBSolver_Tree(self,Ttree,TemperatureC,MeteoData,Int,ExWater,Vwater,Owater,SoilPotW,CiCO2Leaf,ViewFactor,Geometry_m,ParTree,
                      geometry,FractionsGround,FractionsWall,ParSoilGround,ParInterceptionTree,PropOpticalGround,PropOpticalWall,PropOpticalTree,
                      ParVegGround,ParVegTree,SunPosition,ParCalculation,VerticalProfUrban,ColParam):

        """
        ------
        INPUT:
        Ttree: Trees temperature [K]
        TemperatureC: Temperature of the exterior surfaces [K]
        MeteoData: Forcing variables
        Int: Water interception [mm]
        ExWater: Extractable water [mm m^2 m^-2 ground s^-1]
        Vwater: [mm]
        Owater: Water Content [-]
        SoilPotW: [MPa]
        CiCO2Leaf: Leaf Interior  CO2 concentration [umolCO2 mol^-1]
        ViewFactor: View factors
        Geometry_m: Geometric parameters
        ParTree: Trees parameter
        geometry: Normalized geometric parameters
        FractionsGround: Fractions of ground covered by vegetation, impervious, and bare surface
        ParSoilGround: Soil parameters
        ParInterceptionTree: Specific water retained by the tree [mm m^2 VEG area m^-2 plant area]
        PropOpticalGround: Optical properties of the ground (albedo and emissivity)
        PropOpticalWall: Optical properties of the wall (albedo and emissivity)
        PropOpticalTree: Optical properties of the tree (albedo and emissivity)
        ParVegGround: Ground vegetation parameters
        ParVegTree: Trees parameter
        SunPosition: Sun angles
        ParCalculation: General calculation parameters
        VerticalProfUrban: Vertical profile of variables obtained from 1-D model
        ColParam: 1-D model parameters
        -------
        OUTPUT:
        YTree: Energy balance
        EBTree: sensible and latent
        """

        # Update trees temperature in the temperature vector
        TemperatureC_update = copy.copy(TemperatureC)
        TemperatureC_update[5] = float(Ttree[0]) if hasattr(Ttree, '__iter__') else float(Ttree)

        SurfaceHeatFlux = Surface_HeatFlux()
        RadiationCal = RadiationFunctions()

        # Shortwave radiation 
        SWRin_t, SWRout_t, SWRabs_t, SWRabsDir_t, SWRabsDiff_t, SWREB_t = \
            RadiationCal.TotalSWRabsorbed(geometry, FractionsGround, ParTree, PropOpticalGround, PropOpticalWall,
                                        PropOpticalTree, ParVegTree, MeteoData, SunPosition, ViewFactor)

        # Longwave radiation with updated tree surface temperature
        LWRin_t, LWRout_t, LWRabs_t, LWREB_t = \
            RadiationCal.TotalLWRabsorbed(TemperatureC_update, geometry, MeteoData, FractionsGround, PropOpticalGround,
                                        PropOpticalWall, PropOpticalTree, ParTree, ViewFactor)

        # Turbulent heat fluxes from ground and trees to canyon
        HfluxGroundImp, HfluxGroundBare, HfluxGroundVeg, HfluxTree, Eground_imp_pond, Eground_bare_pond, Eground_bare_soil,\
        Eground_veg_int, Eground_veg_pond, Eground_veg_soil, TEground_veg, E_tree_int, TE_tree, Ebare, Eveg, Etree, LEfluxGroundImp,\
        LEfluxGroundBarePond, LEfluxGroundBareSoil, LEfluxGroundVegInt, LEfluxGroundVegPond, LEfluxGroundVegSoil, LTEfluxGroundVeg,\
        LEfluxTreeInt, LTEfluxTree, LEbare, LEveg, LEtree, Ci_sun_tree, Ci_shd_tree, Ci_sun_ground, Ci_shd_ground, rap_can,\
        rap_Htree_In, rb_H, rb_L, r_soil_bare, r_soil_veg, alp_soil_bare, alp_soil_veg, rs_sun_L, rs_shd_L, rs_sun_H,\
        rs_shd_H, Fsun_L, Fshd_L, dw_L = \
            SurfaceHeatFlux.HeatFlux_ground_1D(TemperatureC_update, MeteoData, Geometry_m, geometry, FractionsGround,ParTree,
                                               ParVegGround, ParVegTree, ParSoilGround, SoilPotW, Owater, Vwater, ExWater,
                                               Int, CiCO2Leaf, ParInterceptionTree, ParCalculation,SWRabsDir_t.SWRabsTree,
                                               SWRabsDiff_t.SWRabsTree, SWRabsDir_t.SWRabsGroundVeg,SWRabsDiff_t.SWRabsGroundVeg,
                                               VerticalProfUrban,ColParam)

        if ParTree.trees == 0:
            SWRabs_t.SWRabsTree = 0
            LWRabs_t.LWRabsTree = 0

        # Energy balance for trees
        if ParTree.trees > 0:
            # Net energy flux to leaves [W m^-2]
            YTree = SWRabs_t.SWRabsTree + LWRabs_t.LWRabsTree - HfluxTree - LEfluxTreeInt - LTEfluxTree
        else:
            # When there are no trees we do not need to iteratively solve for tree temperature
            YTree = 0

        class EBTree_Def():
            pass
        self.EBTree = EBTree_Def()
        self.EBTree.HfluxTree = HfluxTree
        self.EBTree.LEfluxTreeInt = LEfluxTreeInt
        self.EBTree.LTEfluxTree = LTEfluxTree
        self.EBTree.LEfluxTree = LEfluxTreeInt + LTEfluxTree
        self.EBTree.EfluxTreeInt = E_tree_int
        self.EBTree.TEfluxTree = TE_tree
        self.EBTree.EfluxTree = E_tree_int + TE_tree
        self.EBTree.CiCO2LeafTreeSun = Ci_sun_tree
        self.EBTree.CiCO2LeafTreeShd = Ci_shd_tree
        self.EBTree.rap_Htree_In = rap_Htree_In
        self.EBTree.rb_HGround = rb_H
        self.EBTree.rs_sunTree = rs_sun_H
        self.EBTree.rs_shdTree = rs_shd_H

        return YTree

    def FSolver_Tree(self,TempVec,TemperatureC,MeteoData,Int,ExWater,Vwater,Owater,SoilPotW,CiCO2Leaf,ViewFactor,Geometry_m,
                     ParTree,geometry,FractionsGround,FractionsWall,ParSoilGround,ParInterceptionTree,PropOpticalGround,PropOpticalWall,
                     PropOpticalTree,ParVegGround,ParVegTree,SunPosition,ParCalculation,VerticalProfUrban,ColParam):

        # Use temperature from previous time step as a starting point
        TTree = copy.copy(TemperatureC[5])

        # For least squares fitting we need a lower bound and an upper bound temperature
        lb = 243
        ub = 373

        Result = least_squares(self.EBSolver_Tree, TTree, bounds=(lb,ub),
                               args=(TemperatureC,MeteoData,Int,ExWater,Vwater,Owater,SoilPotW,CiCO2Leaf,ViewFactor,Geometry_m,
                                     ParTree,geometry,FractionsGround,FractionsWall,ParSoilGround,ParInterceptionTree,PropOpticalGround,
                                     PropOpticalWall,PropOpticalTree,ParVegGround,ParVegTree,SunPosition,ParCalculation,
                                     VerticalProfUrban,ColParam))
        T = Result.x

        # If solver failed, retry with different starting value
        if Result.status < 1:
            TTree = copy.copy(MeteoData.Tatm[itt])

            Result = least_squares(self.EBSolver_Tree, TTree, bounds=(lb, ub),
                                   args=(TemperatureC, MeteoData, Int, ExWater, Vwater, Owater, SoilPotW, CiCO2Leaf,
                                         ViewFactor, Geometry_m,ParTree, geometry, FractionsGround, FractionsWall,ParSoilGround, ParInterceptionTree,
                                         PropOpticalGround,PropOpticalWall, PropOpticalTree, ParVegGround, ParVegTree, SunPosition,
                                         ParCalculation,VerticalProfUrban,ColParam))
            T = Result.x

        for i in range(3):
            if Result.status < 1:
                TTree = TempVec.TTree + i

                Result = least_squares(self.EBSolver_Tree, TTree, bounds=(lb, ub),
                                       args=(TemperatureC, MeteoData, Int, ExWater, Vwater, Owater, SoilPotW, CiCO2Leaf,
                                             ViewFactor, Geometry_m, ParTree, geometry, FractionsGround, FractionsWall,ParSoilGround,
                                             ParInterceptionTree,PropOpticalGround, PropOpticalWall, PropOpticalTree, ParVegGround,
                                             ParVegTree, SunPosition,ParCalculation, VerticalProfUrban,ColParam))
                T = Result.x

        for i in range(3):
            if Result.status < 1:
                TTree = TempVec.TTree - i

                Result = least_squares(self.EBSolver_Tree, TTree, bounds=(lb, ub),
                                       args=(TemperatureC, MeteoData, Int, ExWater, Vwater, Owater, SoilPotW, CiCO2Leaf,
                                             ViewFactor, Geometry_m, ParTree, geometry, FractionsGround,FractionsWall, ParSoilGround,
                                             ParInterceptionTree,PropOpticalGround, PropOpticalWall, PropOpticalTree, ParVegGround,
                                             ParVegTree, SunPosition,ParCalculation, VerticalProfUrban,ColParam))
                T = Result.x

        return T