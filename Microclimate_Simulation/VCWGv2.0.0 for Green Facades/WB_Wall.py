import os
import numpy
import math
from Water_Functions import Water_Calculations
import copy

"""
Compute energy balance at the wall
Developed by Chengjie Li
Urban Spatial Intelligence Research Group at LIESMARS, Wuhan University
Last update: March 2025
"""

class WaterBalanceWall_Def(object):

    def __init__(self,Int_init,TE_init):

        class Int_Def():
            pass
        self.Int = Int_Def()
        self.Int.IntWallVegPlant = Int_init
        self.Int.IntWalltot = Int_init

        self.TEfluxWallVeg = TE_init

        class dInt_dt_Def():
            pass
        self.dInt_dt = dInt_dt_Def()
        self.dInt_dt.dInt_dtWallVegPlant = 0
        self.dInt_dt.dInt_dtWalltot = 0

        class WB_Def():
            pass
        self.WB = WB_Def()
        self.WB.In_veg = 0
        self.WB.veg_tot = 0
        self.WB.Total = 0

        class Run_Def():
            pass
        self.Run = Run_Def()
        self.Run.RunonWallTot = 0
        self.Run.RunoffWallTot = 0
        self.Run.Anthp = 0

    def WBSolver_Wall(self,Ewall_veg,TEfluxWallVeg,MeteoData,
                      ParCalculation,Anthropogenic):
        """
        ------
        INPUT:
        Ewall_veg: Evaporative flux from intercepted water by vegetation [kg m^-2 s^-1]
        TEfluxWallVeg: Transpiration flux from vegetation[kg m^-2 s^-1]
        MeteoData: Forcing variables
        ParCalculation: General calculation parameters
        -------
        OUTPUT:
        dInt_dt: Change in intercepted water (storage)
                 dInt_dtWallVegPlant: Water storage at the vegetation [mm s^-1]
                 dInt_dtWalltot: Total water storage [mm s^-1]
        Int: Intercepted water
             IntWallVegPlant: Intercepted water at the vegetation [mm]
             IntWalltot: Total Intercepted water [mm]
        WB: Water balance (it should be close to zero)
            dIn_veg_dt: Water storage at the vegetation [mm s^-1]
            WBalance_veg_tot: Water balance for the vegetated surface [mm s^-1]
            Total: Total water balance [mm s^-1]
        Run:
            RunonWallTot: Total runon [mm s^-1]
            RunoffWallTot: Total runoff [mm s^-1]
            Anthp: Anthropogenic water [mm s^-1]
        """

        Water_Cal = Water_Calculations()

        Runon_tm1 = copy.copy(self.Run.RunonWallTot)

        Sp_In = 0.2
        LAI = 3
        SAI = 0.001
        # Vegetation
        q_runoff_veg, self.Int.IntWallVegPlant, dIn_veg_dt, WBalance_In_veg = \
            Water_Cal.Water_Vegetation(MeteoData.Rain,Ewall_veg,self.Int.IntWallVegPlant,Sp_In,LAI,
                                       SAI,ParCalculation.rhow,ParCalculation.dts)

        # Set runon of wall as zero
        self.Run.RunonWallTot = 0

        self.Run.RunoffWallTot = q_runoff_veg

        # Water balance for the vegetated surface [mm s^-1]
        WBalance_veg_tot = MeteoData.Rain + Runon_tm1 + Anthropogenic.Waterf_wall/3600 - \
                           (Ewall_veg + TEfluxWallVeg) * 1000 / ParCalculation.rhow - dIn_veg_dt - q_runoff_veg

        # Calculate total water evaporated [mm s^-1]
        E_tot = (Ewall_veg + TEfluxWallVeg) * 1000 / ParCalculation.rhow

        # Calculate total storage [mm s^-1]
        Storage_tot = dIn_veg_dt

        # Calculate total water balance [mm s^-1]
        WBalance_tot = MeteoData.Rain + Runon_tm1 + Anthropogenic.Waterf_wall/3600 - \
                       E_tot - Storage_tot - self.Run.RunoffWallTot

        self.dInt_dt.dInt_dtWallVegPlant = dIn_veg_dt
        self.dInt_dt.dInt_dtWalltot = self.dInt_dt.dInt_dtWallVegPlant

        self.Anthp = Anthropogenic.Waterf_wall/3600

        self.WB.In_veg = WBalance_In_veg
        self.WB.veg_tot = WBalance_veg_tot
        self.WB.Total = WBalance_tot

        self.Int.IntWalltot = self.Int.IntWallVegPlant