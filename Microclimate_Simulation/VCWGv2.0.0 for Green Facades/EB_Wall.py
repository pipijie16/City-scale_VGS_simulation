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
Last update: July 2024
"""

class EnergyBalanceWall_Def(object):

    def __init__(self, CiCO2_Wall_Sun_init, CiCO2_Wall_Shade_init):

        class SWR_Def():
            pass
        self.SWR = SWR_Def()
        self.SWR.SWRabsWallSunVeg = 0
        self.SWR.SWRabsWallShadeVeg = 0
        self.SWR.SWRoutWallSunVeg = 0
        self.SWR.SWRoutWallShadeVeg = 0
        self.SWR.SWRinWallSunVeg = 0
        self.SWR.SWRinWallShadeVeg = 0
        self.SWR.SWR_EB_wallsunveg = 0
        self.SWR.SWR_EB_wallshadeveg = 0

        self.SWR.SWR_abs_totalwall = 0
        self.SWR.SWR_out_totalwall = 0
        self.SWR.SWR_in_totalwall = 0
        self.SWR.SWR_EB_totalwall = 0

        class LWR_Def():
            pass
        self.LWR = LWR_Def()
        self.LWR.LWRabsWallSunVeg = 0
        self.LWR.LWRabsWallShadeVeg = 0
        self.LWR.LWRoutWallSunVeg = 0
        self.LWR.LWRoutWallShadeVeg = 0
        self.LWR.LWRinWallSunVeg = 0
        self.LWR.LWRinWallShadeVeg = 0
        self.LWR.LWR_EB_wallsunveg = 0
        self.LWR.LWR_EB_wallshadeveg = 0

        self.LWR.LWR_abs_totalwall = 0
        self.LWR.LWR_out_totalwall = 0
        self.LWR.LWR_in_totalwall = 0
        self.LWR.LWR_EB_totalwall = 0

        class Hflux_Def():
            pass
        self.Hflux = Hflux_Def()
        self.Hflux.HfluxWallVeg = 0
        self.Hflux.HfluxWall = 0

        class LEflux_Def():
            pass
        self.LEflux = LEflux_Def()
        self.LEflux.LEfluxWallVeg = 0
        self.LEflux.LEfluxWall = 0

        class Eflux_Def():
            pass
        self.Eflux = Eflux_Def()
        self.Eflux.EfluxWallVegInt = 0
        self.Eflux.EfluxWall = 0

        class Cflux_Def():
            pass
        self.Cflux = Cflux_Def()
        self.Cflux.CfluxWall = 0

        class Res_Def():
            pass
        self.Res = Res_Def()
        self.Res.rap_WallVeg = 0
        self.Res.rs_WallSunVeg = 0
        self.Res.rs_WallShadedVeg = 0

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


    def EBSolver_Wall(self, TemperatureC,TemperatureR,MeteoData,Int,Geometry_m,geometry,
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
        PropOpticalWall: Optical properties of the wall (albedo and emissivity)
        ParCalculation: General calculation parameters
        VerticalProfUrban: Vertical profiles of variables obtained from 1-D model
        SunPosition: sun angles
        -------
        OUTPUT:
        SWR: Shortwave radiation
             SWRabsWallSunVeg : Net shortwave radiation at the vegetated sunlit wall [W m^-2]
             SWRabsWallShadeVeg : Net shortwave radiation at the vegetated shaded wall [W m^-2]
             SWRoutWallSunVeg : Outgoing shortwave radiation from the the vegetated sunlit wall [W m^-2]
             SWRoutWallShadeVeg : Outgoing shortwave radiation from the the vegetated shaded wall [W m^-2]
             SWRinWallSunVeg : Incoming shortwave radiation to the the vegetated sunlit wall [W m^-2]
             SWRinWallShadeVeg : Incoming shortwave radiation to the the vegetated shaded wall [W m^-2]
             SWR_EB_wallsunveg : Shortwave radiation energy balance at the vegetated sunlit wall [W m^-2]
             SWR_EB_wallshadeveg : Shortwave radiation energy balance at the vegetated shaded wall [W m^-2]
             SWR_abs_totalwall : Total net shortwave radiation at the wall [W m^-2]
             SWR_out_totalwall : Total outgoing shortwave radiation from the wall [W m^-2]
             SWR_in_totalwall : Total incoming shortwave radiation to the wall [W m^-2]
             SWR_EB_totalwall : Total shortwave radiation energy balance at the wall [W m^-2]
        LWR: Longwave radiation
             LWRabsWallSunVeg : Net longwave radiation at the vegetated sunlit wall [W m^-2]
             LWRabsWallShadeVeg : Net longwave radiation at the vegetated shaded wall [W m^-2]
             LWRoutWallSunVeg : Outgoing longwave radiation from the the vegetated sunlit wall [W m^-2]
             LWRoutWallShadeVeg : Outgoing longwave radiation from the the vegetated shaded wall [W m^-2]
             LWRinWallSunVeg : Incoming longwave radiation to the the vegetated sunlit wall [W m^-2]
             LWRinWallShadeVeg : Incoming longwave radiation to the the vegetated shaded wall [W m^-2]
             LWR_EB_wallsunveg : Longwave radiation energy balance at the vegetated sunlit wall [W m^-2]
             LWR_EB_wallshadeveg : Longwave radiation energy balance at the vegetated shaded wall [W m^-2]
             LWR_abs_totalwall : Total net longwave radiation at the wall [W m^-2]
             LWR_out_totalwall : Total outgoing longwave radiation from the shaded wall [W m^-2]
             LWR_in_totalwall : Total incoming longwave radiation to the shaded wall [W m^-2]
             LWR_EB_totalwall : Total longwave radiation energy balance at the sunlit wall [W m^-2]
        Hflux: Sensible heat fluxes
               HfluxWallVeg : Sensible heat flux from vegetated wall [W m^-2]
               HfluxWall: Total sensible heat flux [W m^-2]
        LEflux: Latent heat fluxes
                LEfluxWallVeg : Latent heat flux from vegetation [W m^-2]
                LEfluxWall: Total latent heat flux [W m^-2]
        Eflux: Evaporative fluxes
               EfluxWallVegInt : Evaporative flux from vegetated shaded surface  [W m^-2]
               EfluxWall: Total evaporative flux [kg m^-2 s^-1]
        Cflux: Wall (conductive) heat fluxes
               CfluxWall: Total conductive heat flux [W m^-2]
        CiCO2: Leaf Interior CO2 concentration
               CiCO2LeafWallVegSun: Sunlit leaf Interior CO2 concentration [umolCO2 mol^-1]
               CiCO2LeafWallVegShd: Shaded leaf Interior CO2 concentration [umolCO2 mol^-1]
        Src: Sink/Source terms in 1-D model
             tvb: Sink/source terms in temperature equation in 1-D model caused by walls
             qhb: Sink/source terms in specific humidity equation in 1-D model
        Res: Resistances
             rap_WallVeg: Aerodynamic resistance near the vegetated wall [s m^-1]
             rs_WallSunVeg: Stomatal resistance of sunlit vegetated wall [s m^-1]
             rs_WallShadedVeg: Stomatal resistance of shaded vegetated wall [s m^-1]
        Tem: Temperature
             foliageTemerpature: Temperature between foliages [K]
        """

        rad = RadiationFunctions()
        
        Geometry_m, ParTree, geometry, FractionsRoof, FractionsGround, WallLayers, ParSoilRoof, \
        ParSoilGround, ParInterceptionTree, PropOpticalRoof, PropOpticalGround, PropOpticalWall, \
        PropOpticalTree, ParThermalRoof, ParThermalGround, ParThermalWall,ParVegRoof,\
        ParVegGround,ParVegTree,Person,ColParam,RSMParam,TimeParam,ViewFactorCal_Param,bld,zone,\
        charLength,BEMParam = Data_Site(VCWG_param_file_path)

        # Longwave radiation absorption
        LWRin_t, LWRout_t, LWRabs, LWREB_t = rad.TotalLWRabsorbed(TemperatureC, geometry, MeteoData, FractionsGround, PropOpticalGround,
                                          PropOpticalWall, PropOpticalTree, ParTree, ViewFactor)

        # Shortwave radiation absorption
        SWRin_t, SWRout_t, SWRabs, SWRabsDir_t, SWRabsDiff_t, SWREB_t = rad.TotalSWRabsorbed(geometry, FractionsGround, ParTree, PropOpticalGround, PropOpticalWall,
                                          PropOpticalTree, ParVegTree, MeteoData, SunPosition, ViewFactor)

        # Shortwave radiation
        # Absorbed shortwave radiation at the vegetated sunlit wall [W m^-2]
        SWRabsWallSunVeg = SWRabs.SWRabsWallSunVeg
        # Absorbed shortwave radiation at the vegetated shaded wall [W m^-2]
        SWRabsWallShadeVeg = SWRabs.SWRabsWallShadeVeg

        # Absorbed total shortwave radiation by the wall [W m^-2]
        SWR_abs_totalwall = SWRabsWallSunVeg + SWRabsWallShadeVeg


        # Outgoing shortwave radiation from the the vegetated sunlit wall [W m^-2]
        SWRoutWallSunVeg = SWRout_t.SWRoutWallSunVeg
        # Outgoing shortwave radiation from the the vegetated shaded wall [W m^-2]
        SWRoutWallShadeVeg = SWRout_t.SWRoutWallShadeVeg

        # Outgoing total shortwave radiation from the total wall [W m^-2]
        SWR_out_totalwall = SWRoutWallSunVeg + SWRoutWallShadeVeg


        # Incoming shortwave radiation to the the vegetated sunlit wall [W m^-2]
        SWRinWallSunVeg = SWRin_t.SWRinWallSunVeg
        # Incoming shortwave radiation to the the vegetated shaded wall [W m^-2]
        SWRinWallShadeVeg = SWRin_t.SWRinWallShadeVeg

        # Incoming total shortwave radiation to the total wall [W m^-2]
        SWR_in_totalwall = SWRinWallSunVeg + SWRinWallShadeVeg

        # Verify conservation of shortwave radiation fluxes (must be zero)
        SWR_EB_wallsunveg = SWRinWallSunVeg - SWRoutWallSunVeg - SWRabsWallSunVeg
        SWR_EB_wallshadeveg = SWRinWallShadeVeg - SWRoutWallShadeVeg - SWRabsWallShadeVeg
        SWR_EB_totalwall = SWR_in_totalwall - SWR_out_totalwall - SWR_abs_totalwall


        # Longwave radiation
        
        # Total absorbed longwave radiation by vegetated sunlit wall [W m^-2]
        LWRabsWallSunVeg = LWRabs.LWRabsWallSunVeg
        # Total absorbed longwave radiation by vegetated shaded wall [W m^-2]
        LWRabsWallShadeVeg = LWRabs.LWRabsWallShadeVeg

        # Total absorbed longwave radiation by the wall [W m^-2]
        LWR_abs_totalwall = LWRabsWallSunVeg + LWRabsWallShadeVeg

        
        # Total outgoing longwave radiation by vegetated wall [W m^-2]
        LWRoutWallSunVeg = LWRout_t.LWRoutWallSunVeg
        # Total outgoing longwave radiation by impervious wall [W m^-2]        
        LWRoutWallShadeVeg = LWRout_t.LWRoutWallShadeVeg
        # Total outgoing longwave radiation from the wall [W m^-2]
        LWR_out_totalwall = LWRoutWallSunVeg + LWRoutWallShadeVeg

        # Total incoming longwave radiation to impervious wall [W m^-2]
        LWRinWallSunVeg = LWRin_t.LWRinWallSunVeg
        # Total incoming longwave radiation to vegetated wall [W m^-2]
        LWRinWallShadeVeg = LWRin_t.LWRinWallShadeVeg
        # Total incoming longwave radiation to the wall [W m^-2]
        LWR_in_totalwall = LWRinWallSunVeg + LWRinWallShadeVeg


        # Verify conservation of longwave radiation fluxes (must be zero)
        LWR_EB_wallsunveg = LWRinWallSunVeg - LWRoutWallSunVeg - LWRabsWallSunVeg
        LWR_EB_wallshadeveg = LWRinWallShadeVeg - LWRoutWallShadeVeg - LWRabsWallShadeVeg
        LWR_EB_totalwall = LWR_in_totalwall - LWR_out_totalwall - LWR_abs_totalwall


        # Calculate sensible and latent heat
        # Calculate sensible heat flux from vegetated wall [W m^-2]
        SurfaceHeatFlux = Surface_HeatFlux()
        HfluxWallVeg, Ewsun, Ewshade, LEwsun, LEwshade, LEwveg, rap_WallVeg, rs_WallSunVeg, rs_WallShadedVeg = \
            SurfaceHeatFlux.HeatFlux_wall(MeteoData, TemperatureC, Geometry_m,geometry,VerticalProfUrban,FractionsGround,ParCalculation,
                                          PropOpticalGround,PropOpticalWall,PropOpticalTree,ParVegTree,ParTree,SunPosition,ColParam,ViewFactor)
        # Calculate total sensible heat flux [W m^-2]
        HfluxWall = HfluxWallVeg
        
        self.Src.tvb = SurfaceHeatFlux.tvb_wall

        # Longwave radiation absorption
        LWRabsWallVeg = (LWRabs.LWRabsWallSunVeg + LWRabs.LWRabsWallShadeVeg) / 2
        # Shortwave radiation absorption
        SWRabsWallVeg = (SWRabs.SWRabsWallSunVeg + SWRabs.SWRabsWallShadeVeg) / 2

        # Call the Penman-Monteith calculation function
        Tdepth_rural_init = 300.0
        CiCO2Ground_Sun_Rural_init = 400.0
        CiCO2Ground_Shade_Rural_init = 400.0

        # soil heat flux [W m^-2]
        G_wallveg = 0
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
        TwsunVeg = TemperatureC[3]
        TwshadeVeg = TemperatureC[4]

        Tavg_canyon = numpy.mean(VerticalProfUrban.th[0:Geometry_m.nz_u])
        
        # Air specific heat  [J kg^-1 K^-1]
        cp_atm = 1005 + (((Tavg_canyon - 273.15) + 23.15) ** 2) / 3364
        # dry air density [kg m^-3]
        rho_atm = numpy.mean(VerticalProfUrban.rho[:Geometry_m.nz_u])
        # Latent heat vaporization/condensation [J kg^-1]
        L_heat = 1000 * (2501.3 - 2.361 * (Tavg_canyon - 273.15))

        # Wall exterior surface temperature
        Tw = (TwsunVeg + TwshadeVeg) / 2

        # Stefan-Boltzmann constant
        sigma = 5.67 * 10 ** (-8)

        # Leaf absorptivity
        epsilon_leaf = 0.96

        # Air specific heat [J kg^-1 K^-1]
        cp_atm = 1005 + (((Tavg_canyon - 273.15) + 23.15) ** 2) / 3364

        # Initial Tleaf (start with air temperature)
        Tleaf = MeteoData.Tatm

        # Constants
        rl = 100  # Leaf boundary resistance [s m^-1]
        R = 287  # Gas constant for dry air [J kg^-1 K^-1]

        # the transmissivity of radiation through the plant layer
        tau = 0.22

        # bulk transfer coefficient for sensible heat from leaf to air [m s^-1]
        b = max(1e-6, 0.01 * (1 + 0.3 / MeteoData.Uatm))

        LWRabsVeg = LWRabsWallVeg
        SWRabsVeg = SWRabsWallVeg
                
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
            
            grad_q = (esat_Tleaf - esat_Taf) / 0.1
            grad_T = (Tleaf - Taf) / 0.1
            D = 2.5e-5
            diff_term = -((2000.0 - cp_atm) / cp_atm) * (D * grad_q * grad_T)
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

        # Total latent heat flux [W m^-2]
        LEfluxWall = LEfluxWallVeg

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
        # Total evaporation flux from intercepted water by vegetation [kg m^-2 s^-1]
        EfluxWall = EfluxWallVeg


        # Save sink/source terms, which will be used in 1-D model for specific humidity (evaporative flux) [kg kg^-1 m s^-1]
        # and for temperature (sensible kinematic heat flux) [K m s^-1]
        self.Src.qhb = LEfluxWallVeg / (L_heat * rho_atm)
        # Radiation fluxes [W m^-2]
        self.SWR.SWRabsWallSunVeg = SWRabsWallSunVeg
        self.SWR.SWRabsWallShadeVeg = SWRabsWallShadeVeg
        self.SWR.SWRoutWallSunVeg = SWRoutWallSunVeg
        self.SWR.SWRoutWallShadeVeg = SWRoutWallShadeVeg
        self.SWR.SWRinWallSunVeg = SWRinWallSunVeg
        self.SWR.SWRinWallShadeVeg = SWRinWallShadeVeg
        self.SWR.SWR_EB_wallsunveg = SWR_EB_wallsunveg
        self.SWR.SWR_EB_wallshadeveg = SWR_EB_wallshadeveg

        self.SWR.SWR_abs_totalwall = SWR_abs_totalwall
        self.SWR.SWR_out_totalwall = SWR_out_totalwall
        self.SWR.SWR_in_totalwall = SWR_in_totalwall
        self.SWR.SWR_EB_totalwall = SWR_EB_totalwall

        self.LWR.LWRabsWallSunVeg = LWRabsWallSunVeg
        self.LWR.LWRabsWallShadeVeg = LWRabsWallShadeVeg
        self.LWR.LWRoutWallSunVeg = LWRoutWallSunVeg
        self.LWR.LWRoutWallShadeVeg = LWRoutWallShadeVeg
        self.LWR.LWRinWallSunVeg = LWRinWallSunVeg
        self.LWR.LWRinWallShadeVeg = LWRinWallShadeVeg
        self.LWR.LWR_EB_wallsunveg = LWR_EB_wallsunveg
        self.LWR.LWR_EB_wallshadeveg = LWR_EB_wallshadeveg

        self.LWR.LWR_abs_totalwall = LWR_abs_totalwall
        self.LWR.LWR_out_totalwall = LWR_out_totalwall
        self.LWR.LWR_in_totalwall = LWR_in_totalwall
        self.LWR.LWR_EB_totalwall = LWR_EB_totalwall

        # Sensible heat fluxes [W m^-2]
        self.Hflux.HfluxWallVeg = HfluxWallVeg
        self.Hflux.HfluxWall = HfluxWall

        # Latent heat fluxes [W m^-2]
        self.LEflux.LEfluxWallVeg = LEfluxWallVeg
        self.LEflux.LEfluxWall = LEfluxWall

        # Evaporative fluxes [kg m^-2 s^-1]
        self.Eflux.EfluxWallVegInt = EfluxWallVeg
        self.Eflux.EfluxWall = EfluxWall

        SWRabsWallVeg = (SWRabsWallSunVeg + SWRabsWallShadeVeg) / 2
        LWRabsWallVeg = (LWRabsWallSunVeg + LWRabsWallShadeVeg) / 2

        # Wall heat conductive fluxes [W m^-2]
        self.Cflux.CfluxWall = SWRabsWallVeg + LWRabsWallVeg - HfluxWallVeg - LEfluxWallVeg

        # Resistances
        self.Res.rap_WallVeg = rap_WallVeg
        self.Res.rs_WallSunVeg = EB_canyon.Res.rs_WallSunVeg
        self.Res.rs_WallShadedVeg = EB_canyon.Res.rs_WallShadedVeg

        self.Tem.Taf = Taf
