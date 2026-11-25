import os
import numpy
import math
from pprint import pprint
from scipy.interpolate import interp1d
from scipy.optimize import fsolve
from Simparam import SimParam
import matplotlib.pyplot as plt
from psychrometrics import psychrometrics
from weather import Weather
from EB_Canyon import EnergyBalanceCanyon_Def
from WB_Canyon import WaterBalanceCanyon_Def
from UrbanSurfaceHeatFlux import Surface_HeatFlux
from WaterFunctionsDef import WaterVegetationDef
from Soil_Functions import Soil_Calculations
from scipy.integrate import odeint
from Resistance_Functions import Ressitance_Calculations
from Radiation_Functions import RadiationFunctions
from Read_Input import Data_Site
from scipy.optimize import least_squares
import copy

"""
Compute energy balance at the wall
Developed by Chengjie Li
Urban Spatial Intelligence Research Group at LIESMARS, Wuhan University
Last update: March 2025
"""

class EnergyBalanceWall_Def(object):

    def __init__(self, CiCO2_Wall_Sun_init, CiCO2_Wall_Shade_init):

        class SWR_Def():
            pass
        self.SWR = SWR_Def()
        self.SWR.SWRabsWallImp = 0
        self.SWR.SWRoutWallImp = 0
        self.SWR.SWRinWallImp = 0
        self.SWR.SWREBWallImp = 0
        self.SWR.SWRabsWallVeg = 0
        self.SWR.SWRoutWallVeg = 0
        self.SWR.SWRinWallVeg = 0
        self.SWR.SWREBWallVeg = 0
        self.SWR.SWRabsTotalWall = 0
        self.SWR.SWRoutTotalWall = 0
        self.SWR.SWRinTotalWall = 0
        self.SWR.SWREBTotalWall = 0

        class LWR_Def():
            pass
        self.LWR = LWR_Def()
        self.LWR.LWRabsWallImp = 0
        self.LWR.LWRoutWallImp = 0
        self.LWR.LWRinWallImp = 0
        self.LWR.LWREBWallImp = 0
        self.LWR.LWRabsWallVeg = 0
        self.LWR.LWRoutWallVeg = 0
        self.LWR.LWRinWallVeg = 0
        self.LWR.LWREBWallVeg = 0
        self.LWR.LWRabsTotalWall = 0
        self.LWR.LWRoutTotalWall = 0
        self.LWR.LWRinTotalWall = 0
        self.LWR.LWREBTotalWall = 0

        class Hflux_Def():
            pass
        self.Hflux = Hflux_Def()
        self.Hflux.HfluxWallVeg = 0
        self.Hflux.HfluxWallImp = 0
        self.Hflux.HfluxWall = 0

        class LEflux_Def():
            pass
        self.LEflux = LEflux_Def()
        self.LEflux.LEfluxWallVeg = 0
        self.LEflux.LEfluxWallVegSoil = 0
        self.LEflux.LEfluxWall = 0

        class Eflux_Def():
            pass
        self.Eflux = Eflux_Def()
        self.Eflux.EfluxWallVeg = 0
        self.Eflux.EfluxWallVegSoil = 0
        self.Eflux.EfluxWall = 0
        self.Eflux.TEfluxWallVeg = 0.0

        class Cflux_Def():
            pass
        self.Cflux = Cflux_Def()
        self.Cflux.CfluxWallImp = 0
        self.Cflux.CfluxWallVeg = 0

        class Res_Def():
            pass
        self.Res = Res_Def()
        self.Res.rap_WallVeg = 0
        self.Res.rs_WallImp = 0
        self.Res.rs_WallVeg = 0
        self.Res.r_soilWall = 0

        class CiCO2_Def():
            pass
        self.CiCO2 = CiCO2_Def()
        self.CiCO2.CiCO2LeafWallVegSun = CiCO2_Wall_Sun_init
        self.CiCO2.CiCO2LeafWallVegShd = CiCO2_Wall_Shade_init

        class Src_Def():
            pass
        self.Src = Src_Def()
        self.Src.tvb = None
        self.Src.qhb = None

        class Temperature():
            pass
        self.Tem = Temperature()
        self.Tem.Taf = 0

    def EBSolver_Wall(self, TemperatureC,TempVec,TemperatureR,MeteoData,Owater,Int,Geometry_m,FractionsWall,ParSoilWall,geometry,
                      PropOpticalWall,ParCalculation,VerticalProfUrban,SunPosition,VCWG_param_file_path,ViewFactor):
        """
        ------
        INPUT:
        TemperatureR: Temperature of the exterior surfaces [K]
        MeteoData: Forcing variables
        Int: Intercepted water
        ExWater: Maximum extractable water [mm m^2 m^-2 wall s^-1]
        Vwater: Volume of water in each soil layer per unit area [mm]
        Owater: Water content (soil moisture) in each layer [-]
        Geometry_m: Geometric parameters
        FractionsWall: Fractions of wall covered by vegetation and impervious surface
        PropOpticalWall: Optical properties of the wall (albedo and emissivity)
        ParCalculation: General calculation parameters
        VerticalProfUrban: Vertical profiles of variables obtained from 1-D model
        SunPosition: sun angles
        -------
        OUTPUT:
        SWR: Shortwave radiation
             SWRabsWallImp: Net shortwave radiation at the impervious surface [W m^-2]
             SWRoutWallImp: Outgoing shortwave radiation from the the impervious surface [W m^-2]
             SWRinWallImp: Incoming shortwave radiation to the the impervious surface [W m^-2]
             SWREBWallImp: Shortwave radiation energy balance at the impervious surface [W m^-2]
             SWRabsWallVeg: Net shortwave radiation at the vegetated surface [W m^-2]
             SWRoutWallVeg: Outgoing shortwave radiation from the the vegetated surface [W m^-2]
             SWRinWallVeg: Incoming shortwave radiation to the the vegetated surface [W m^-2]
             SWREBWallVeg: Shortwave radiation energy balance at the vegetated surface [W m^-2]
             SWRabsTotalWall: Total net shortwave radiation [W m^-2]
             SWRoutTotalWall: Total outgoing shortwave radiation [W m^-2]
             SWRinTotalWall: Total incoming shortwave radiation [W m^-2]
             SWREBTotalWall: Total shortwave radiation energy balance [W m^-2]
        LWR: Longwave radiation
             LWRabsWallImp: Net longwave radiation at the impervious surface [W m^-2]
             LWRoutWallImp: Outgoing longwave radiation from the the impervious surface [W m^-2]
             LWRinWallImp: Incoming longwave radiation to the the impervious surface [W m^-2]
             LWREBWallImp: Longwave radiation energy balance at the impervious surface [W m^-2]
             LWRabsWallVeg: Net longwave radiation at the vegetated surface [W m^-2]
             LWRoutWallVeg: Outgoing longwave radiation from the the impervious surface [W m^-2]
             LWRinWallVeg: Incoming longwave radiation to the the vegetated surface [W m^-2]
             LWREBWallVeg: Longwave radiation energy balance at the vegetated surface [W m^-2]
             LWRabsTotalWall: Total net longwave radiation [W m^-2]
             LWRoutTotalWall: Total outgoing longwave radiation [W m^-2]
             LWRinTotalWall: Total incoming longwave radiation [W m^-2]
             LWREBTotalWall: Total longwave radiation energy balance [W m^-2]
        Hflux: Sensible heat fluxes
               HfluxWallVeg: Sensible heat flux from vegetated surface [W m^-2]
               HfluxWallImp: Sensible heat flux from impervious surface [W m^-2]
               HfluxWall: Total sensible heat flux [W m^-2]
        LEflux: Latent heat fluxes
                LEfluxWallVeg: Total latent heat flux from vegetated surface and soil [W m^-2]
                LEfluxWall: Total latent heat flux [W m^-2]
        Eflux: Evaporative fluxes
               EfluxWallVeg: Total evaporative flux from vegetated surface [kg m^-2 s^-1]
               EfluxWall: Total evaporative flux [kg m^-2 s^-1]
        Cflux: Conductive heat fluxes
               CfluxWall: Total conductive heat flux [W m^-2]
        CiCO2: Leaf Interior CO2 concentration
               CiCO2LeafWallVegSun: Sunlit leaf Interior CO2 concentration [umolCO2 mol^-1]
               CiCO2LeafWallVegShd: Shaded leaf Interior CO2 concentration [umolCO2 mol^-1]
        Src: Sink/Source terms in 1-D model
             tvb: Sink/source terms in temperature equation in 1-D model caused by walls
             qhb: Sink/source terms in specific humidity equation in 1-D model
        Res: Resistances
             rap_WallVeg: Aerodynamic resistance near the vegetated wall [s m^-1]
             rs_WallImp: Stomatal resistance of sunlit impervious wall [s m^-1]
             rs_WallVeg: Stomatal resistance of shaded vegetated wall [s m^-1]
        Tem: Temperature
             foliageTemerpature: Temperature between foliages [K]
        """

        rad = RadiationFunctions()
        
        tau = 0.22  # the transmissivity of radiation through the plant layer
        
        Geometry_m, ParTree, geometry, FractionsRoof, FractionsWall, FractionsGround, WallLayers, ParSoilRoof, \
        ParSoilGround, ParSoilWall, ParInterceptionTree, PropOpticalRoof, PropOpticalGround, PropOpticalWall, \
        PropOpticalTree, ParThermalRoof, ParThermalGround, ParThermalWall,ParVegRoof,\
        ParVegGround,ParVegTree,ParVegWall,Person,ColParam,RSMParam,TimeParam,ViewFactorCal_Param,bld,zone,\
        charLength,BEMParam = Data_Site(VCWG_param_file_path)

        # Longwave radiation absorption
        LWRin_t, LWRout_t, LWRabs, LWREB_t = rad.TotalLWRabsorbed(TemperatureC, geometry, MeteoData, FractionsGround, PropOpticalGround,
                                          PropOpticalWall, PropOpticalTree, ParTree, ViewFactor)

        # Shortwave radiation absorption
        SWRin_t, SWRout_t, SWRabs, SWRabsDir_t, SWRabsDiff_t, SWREB_t = rad.TotalSWRabsorbed(geometry, FractionsGround, ParTree, PropOpticalGround, PropOpticalWall,
                                          PropOpticalTree, ParVegTree, MeteoData, SunPosition, ViewFactor)

        # Shortwave radiation
        alpha_soil = 0.7 # Absorptivity of shortwave radiation for wall
        # Absorbed total shortwave radiation by vegetated wall [W m^-2]
        SWR_abs_wallveg = SWRabs.SWRabsWallVeg * tau * alpha_soil
        # Absorbed total shortwave radiation by impervious wall [W m^-2]
        SWR_abs_wallimp = SWRabs.SWRabsWallImp
        # Absorbed total shortwave radiation by the wall [W m^-2]
        SWR_abs_totalwall = SWR_abs_wallimp * FractionsWall.fimp + SWR_abs_wallveg * FractionsWall.fveg

        # Outgoing total shortwave radiation from the vegetated wall [W m^-2]
        SWR_out_wallveg = PropOpticalWall.aveg * SWRout_t.SWRoutWallVeg * tau * alpha_soil
        # Outgoing total shortwave radiation from the impervious wall [W m^-2]
        SWR_out_wallimp = PropOpticalWall.aimp * SWRout_t.SWRoutWallImp
        # Outgoing total shortwave radiation from the total wall [W m^-2]
        SWR_out_totalwall = SWR_out_wallimp * FractionsWall.fimp + SWR_out_wallveg * FractionsWall.fveg

        # Incoming total shortwave radiation to the impervious wall [W m^-2]
        SWR_in_wallimp = SWRin_t.SWRinWallImp
        # Incoming total shortwave radiation to the vegetated wall [W m^-2]
        SWR_in_wallveg = SWRin_t.SWRinWallVeg * tau * alpha_soil
        # Incoming total shortwave radiation to the total wall [W m^-2]
        SWR_in_totalwall = SWR_in_wallimp * FractionsWall.fimp + SWR_in_wallveg * FractionsWall.fveg

        # Verify conservation of shortwave radiation fluxes (must be zero)
        SWR_EB_wallimp = SWR_in_wallimp - SWR_out_wallimp - SWR_abs_wallimp
        SWR_EB_wallveg = SWR_in_wallveg - SWR_out_wallveg - SWR_abs_wallveg
        SWR_EB_totalwall = SWR_in_totalwall - SWR_out_totalwall - SWR_abs_totalwall

        # Longwave radiation
        epsilon_soil = 0.95 # Emissivity of wall
        # Total absorbed longwave radiation by vegetated wall [W m^-2]
        LWR_abs_wallveg = LWRabs.LWRabsWallVeg * tau * epsilon_soil
        # Total absorbed longwave radiation by impervious wall [W m^-2]
        LWR_abs_wallimp = LWRabs.LWRabsWallImp
        # Total absorbed longwave radiation by the wall [W m^-2]
        LWR_abs_totalwall = LWR_abs_wallimp * FractionsWall.fimp + LWR_abs_wallveg * FractionsWall.fveg

        # Total outgoing longwave radiation by vegetated wall [W m^-2]
        LWR_out_wallveg = LWRout_t.LWRoutWallVeg * tau * epsilon_soil
        # Total outgoing longwave radiation by impervious wall [W m^-2]
        LWR_out_wallimp = LWRout_t.LWRoutWallImp
        # Total outgoing longwave radiation from the wall [W m^-2]
        LWR_out_totalwall = LWR_out_wallimp * FractionsWall.fimp + LWR_out_wallveg * FractionsWall.fveg

        # Total incoming longwave radiation to impervious wall [W m^-2]
        LWR_in_wallimp = LWRin_t.LWRinWallImp
        # Total incoming longwave radiation to vegetated wall [W m^-2]
        LWR_in_wallveg = LWRin_t.LWRinWallVeg * tau * epsilon_soil
        # Total incoming longwave radiation to the wall [W m^-2]
        LWR_in_totalwall = LWR_in_wallimp * FractionsWall.fimp + LWR_in_wallveg * FractionsWall.fveg

        # Verify conservation of longwave radiation fluxes (must be zero)
        LWR_EB_wallimp = LWR_in_wallimp - LWR_out_wallimp - LWR_abs_wallimp
        LWR_EB_wallveg = LWR_in_wallveg - LWR_out_wallveg - LWR_abs_wallveg
        LWR_EB_totalwall = LWR_in_totalwall - LWR_out_totalwall - LWR_abs_totalwall

        # Calculate sensible and latent heat
        # Calculate sensible heat flux from vegetated wall [W m^-2]
        SurfaceHeatFlux = Surface_HeatFlux()
        HfluxWallVeg, HfluxWallImp, Ewall_veg_soil, Ewsun, Ewshade, LEwsun, LEwshade, LEwveg, LEfluxWallVegSoil,\
        rap_WallVeg, rs_soilWallSunVeg, rs_soilWallShadedVeg, rs_WallImp, rs_WallVeg = \
            SurfaceHeatFlux.HeatFlux_wall(MeteoData, TemperatureC, Geometry_m,geometry,VerticalProfUrban,FractionsGround,ParCalculation,
                                          PropOpticalGround,PropOpticalWall,PropOpticalTree,ParVegTree,ParTree,Owater,SunPosition,ColParam,ViewFactor,TempVec)
        
        # Calculate total sensible heat flux [W m^-2]
        HfluxWall = HfluxWallImp * FractionsWall.fimp + HfluxWallVeg * FractionsWall.fveg

        self.Src.tvb = SurfaceHeatFlux.tvb_wall

        # Call the Penman-Monteith calculation function
        Tdepth_rural_init = 300.0
        CiCO2Ground_Sun_Rural_init = 400.0
        CiCO2Ground_Shade_Rural_init = 400.0

        # the transmissivity of radiation through the plant layer
        tau = 0.22

        # Total Thermal Capacity Soil [K m^2 J^-1]
        CTt = 2 * (numpy.sqrt(numpy.pi / (ParThermalWall.lan_dry * ParThermalWall.cv_s * tau)))

        # Height of measured wind speed [m]
        h_wind = 10
        
        CiCO2Ground_Sun_init = 400.0
        CiCO2Ground_Shade_init = 400.0
        CiCO2Tree_Sun_init = 400.0
        CiCO2Tree_Shade_init = 400.0

        Tdepth_gimp_init = 300.0
        Tdepth_gbare_init = 300.0
        Tdepth_gveg_init = 300.0
        Ttree_init = 300.0

        CiCO2LeafWallVegSun_init = 400.0
        CiCO2LeafWallVegShd_init = 400.0
        
        EB_canyon = EnergyBalanceCanyon_Def(CiCO2Tree_Sun_init,CiCO2Tree_Shade_init,CiCO2Ground_Sun_init,CiCO2Ground_Shade_init,CiCO2LeafWallVegSun_init,
                                            CiCO2LeafWallVegShd_init,Tdepth_gimp_init,Tdepth_gbare_init,Tdepth_gveg_init,Ttree_init)
        
        ResistanceCal = Ressitance_Calculations()

        # Leaf area index of vegetated wall
        LAI = 3
        # Stem area index for the wall vegetation [-]
        SAI = 0.001
        # Air density [kg m^-3]
        rho_atm = copy.copy(VerticalProfUrban.rho[Geometry_m.nz_u])
        # Specific humidity at canyon
        qcanyon = copy.copy(VerticalProfUrban.qn[0])
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
        
        # Air specific heat  [J kg^-1 K^-1]
        cp_atm = 1005 + (((Tavg_canyon - 273.15) + 23.15) ** 2) / 3364
        # dry air density [kg m^-3]
        rho_atm = numpy.mean(VerticalProfUrban.rho[:Geometry_m.nz_u])
        # Latent heat vaporization/condensation [J kg^-1]
        L_heat = 1000 * (2501.3 - 2.361 * (Tavg_canyon - 273.15))

        # Stefan-Boltzmann constant
        sigma = 5.67 * 10 ** (-8)

        # Leaf absorptivity
        epsilon_leaf = 0.96

        # Air specific heat [J kg^-1 K^-1]
        cp_atm = 1005 + (((Tavg_canyon - 273.15) + 23.15) ** 2) / 3364

        # Initial Tleaf (start with air temperature)
        Tleaf = MeteoData.Tatm

        Tempback_2 = Tleaf

        Tdptm1 = TemperatureC[6]

        # Constants
        rl = 100  # Leaf boundary resistance [s m^-1]
        R = 287  # Gas constant for dry air [J kg^-1 K^-1]

        # the transmissivity of radiation through the plant layer
        tau = 0.22

        SurfaceHeatFlux = Surface_HeatFlux()
        
        # bulk transfer coefficient for sensible heat from leaf to air [m s^-1]
        U_leaf = max(0.1, float(numpy.mean(numpy.sqrt(
            numpy.asarray(VerticalProfUrban.vx[:Geometry_m.nz_u], dtype=float) ** 2 +
            numpy.asarray(VerticalProfUrban.vy[:Geometry_m.nz_u], dtype=float) ** 2))))
        b = max(1e-6, 0.01 * (U_leaf + 0.3))

        LWRabsVeg = LWRabs.LWRabsWallVeg
        SWRabsVeg = SWRabs.SWRabsWallVeg
                
        # Iterate to balance energy (stabilized update using numeric derivative, soil included)
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

            error = SWRabsVeg + LWRabsVeg + XR - H_leaf_adjusted - LEfluxWallVeg - G_wallveg

            if abs(error) < 5.0:
                break

            dFlux_dT = 1.1 * LAI * rho_af * cp_atm * b + (rho_atm * cp_atm / gamma) * (4098.0 * esat_Tleaf / (237.3 + Tleaf_C)**2) / (rap_WallVeg + rs_leaf) + 4 * sigma * Tleaf**3
            dT = error / max(dFlux_dT, 10.0)
            dT = max(-0.5, min(0.5, dT))
            Tleaf = max(260.0, min(350.0, Tleaf + dT))

        # Temperature between foliages
        Taf = tau * MeteoData.Tatm + (1 - tau) * (0.3 * MeteoData.Tatm + 0.6 * Tleaf + 0.1 * Tdptm1)
        
        # Leaf boundary resistance
        rb_L = ResistanceCal.Leaf_BR(u_Lveg, Taf - 273.15, Tavg_canyon - 273.15, d_leaf, alpha)

        # vapor pressure saturation at vegetated wall [Pa]
        esat_veg = 611 * numpy.exp(17.27 * (Tavg_canyon - 273.16) / (237.3 + (Tavg_canyon - 273.16)))
        # Saturated specific humidity at vegetated wall [kg kg^-1]
        qsat_veg = numpy.round((0.622 * esat_veg) / (MeteoData.Pre - 0.378 * esat_veg),4)
        # Potential evaporation from intercepted water on vegetated wall [kg m^-2 s^-1]
        if dw_L > 1e-4:
            Eveg_int_pot = rho_atm * (qsat_veg - qcanyon) / (rb_L / ((LAI + SAI) * dw_L) + rap_WallVeg)
        else:
            Eveg_int_pot = 0.0
        # Evaporative flux from vegetated surface [W m^-2]
        EfluxWallVegSoil = Ewall_veg_soil
        EfluxWallVeg = Eveg_int_pot + EfluxWallVegSoil
        # Total evaporation flux from intercepted water by vegetation [kg m^-2 s^-1]
        EfluxWall = EfluxWallVeg * FractionsWall.fveg
        
        r_soil = rs_soilWallSunVeg

        # Save sink/source terms, which will be used in 1-D model for specific humidity (evaporative flux) [kg kg^-1 m s^-1]
        # and for temperature (sensible kinematic heat flux) [K m s^-1]
        self.Src.qhb = (LEfluxWallVeg / L_heat + Eveg_int_pot + EfluxWallVegSoil) / rho_atm
        # Radiation fluxes [W m^-2]
        self.SWR.SWRabsWallImp = SWR_abs_wallimp
        self.SWR.SWRoutWallImp = SWR_out_wallimp
        self.SWR.SWRinWallImp = SWR_in_wallimp
        self.SWR.SWREBWallImp = SWR_EB_wallimp
        self.SWR.SWRabsWallVeg = SWR_abs_wallveg
        self.SWR.SWRoutWallVeg = SWR_out_wallveg
        self.SWR.SWRinWallVeg = SWR_in_wallveg
        self.SWR.SWREBWallVeg = SWR_EB_wallveg
        self.SWR.SWRabsTotalWall = SWR_abs_totalwall
        self.SWR.SWRoutTotalWall = SWR_out_totalwall
        self.SWR.SWRinTotalWall = SWR_in_totalwall
        self.SWR.SWREBTotalWall = SWR_EB_totalwall

        self.LWR.LWRabsWallImp = LWR_abs_wallimp
        self.LWR.LWRoutWallImp = LWR_out_wallimp
        self.LWR.LWRinWallImp = LWR_in_wallimp
        self.LWR.LWREBWallImp = LWR_EB_wallimp
        self.LWR.LWRabsWallVeg = LWR_abs_wallveg
        self.LWR.LWRoutWallVeg = LWR_out_wallveg
        self.LWR.LWRinWallVeg = LWR_in_wallveg
        self.LWR.LWREBWallVeg = LWR_EB_wallveg
        self.LWR.LWRabsTotalWall = LWR_abs_totalwall
        self.LWR.LWRoutTotalWall = LWR_out_totalwall
        self.LWR.LWRinTotalWall = LWR_in_totalwall
        self.LWR.LWREBTotalWall = LWR_EB_totalwall

        # Sensible heat fluxes [W m^-2]
        self.Hflux.HfluxWallVeg = HfluxWallVeg
        self.Hflux.HfluxWallImp = HfluxWallImp
        self.Hflux.HfluxWall = HfluxWall

        # Latent heat fluxes [W m^-2]
        self.LEflux.LEfluxWallVeg = LEfluxWallVeg
        self.Eflux.TEfluxWallVeg = LEfluxWallVeg / max(L_heat, 1.0e-12)
        self.LEflux.LEfluxWallVegSoil = LEfluxWallVegSoil
        self.LEflux.LEfluxWall = LEfluxWallVeg + LEfluxWallVegSoil

        # Evaporative fluxes [kg m^-2 s^-1]
        self.Eflux.EfluxWallVegInt = Eveg_int_pot
        self.Eflux.EfluxWall = EfluxWall
        self.Eflux.EfluxWallVegSoil = EfluxWallVegSoil

        # Wall heat conductive fluxes [W m^-2]
        self.Cflux.CfluxWallImp = EB_canyon.Gflux.CfluxWallVeg
        self.Cflux.CfluxWallVeg = EB_canyon.Gflux.CfluxWallVeg

        # Resistances
        self.Res.rap_WallVeg = rap_WallVeg
        self.Res.rs_WallImp = EB_canyon.Res.rs_WallImp
        self.Res.rs_WallVeg = EB_canyon.Res.rs_WallVeg
        self.Res.r_soilWall = r_soil

        self.Tem.Taf = Taf
