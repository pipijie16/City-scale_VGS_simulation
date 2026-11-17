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

    def __init__(self,Int_init,TE_init,Owater_init,E_init,ParSoilWall,ExWater_init,V_init,SoilPotW_init):

        class Int_Def():
            pass
        self.Int = Int_Def()
        self.Int.IntWallImp = Int_init
        self.Int.IntWallVegPlant = Int_init
        self.Int.IntWalltot = Int_init

        self.Owater_OwWallSoilVeg = [Owater_init for i in range(ParSoilWall.ms)]
        self.TEfluxWallVeg = TE_init
        self.EfluxWallVegSoil = E_init
        self.ExWaterWall_L = [ExWater_init for i in range(ParSoilWall.ms)]
        self.VWallSoil = V_init
        self.SoilPotWWall_L = SoilPotW_init

        class dInt_dt_Def():
            pass
        self.dInt_dt = dInt_dt_Def()
        self.dInt_dt.dInt_dtWallVegPlant = 0
        self.dInt_dt.dInt_dtWalltot = 0

        class WB_Def():
            pass
        self.WB = WB_Def()
        self.WB.In_veg = 0
        self.WB.imp_tot = 0
        self.WB.veg_tot = 0
        self.WB.soil = 0
        self.WB.Total = 0

        class Run_Def():
            pass
        self.Run = Run_Def()
        self.Run.RunonWallTot = 0
        self.Run.RunoffWallTot = 0
        self.Run.QWallImp = 0
        self.Run.QWallVeg = 0
        self.Run.QWallVegSoil = 0
        self.Run.Anthp = 0

    def WBSolver_Wall(self,Ewall_imp,Ewall_veg,EfluxWallVegSoil_EB,TEfluxWallVeg_EB,MeteoData,FractionsWall,
                      ParSoilWall,ParCalculation,ParVegWall,Anthropogenic):
        """
        ------
        INPUT:
        Ewall_veg: Evaporative flux from intercepted water by vegetation [kg m^-2 s^-1]
        EfluxWallVegSoil_EB: Evaporative flux from soil under vegetation (first layer) [kg m^-2 s^-1]
        TEfluxWallVeg: Transpiration flux from vegetation[kg m^-2 s^-1]
        MeteoData: Forcing variables
        ParCalculation: General calculation parameters
        -------
        OUTPUT:
        dInt_dt: Change in intercepted water (storage)
                 dInt_dtWallVegPlant: Water storage at the vegetation [mm s^-1]
                 dInt_dtWalltot: Total water storage [mm s^-1]
        VWallSoil: Volume of water in each soil layer per unit area [mm]
        SoilPotWWall_L: Soil Water Potential for Second Layer of Vegetation [MPa]
        ExWaterWall_L: Maximum extractable water [mm m^2 m^-2 ground s^-1]
        Int: Intercepted water
             IntWallImp: Intercepted water at the impervious wall [mm]
             IntWallVegPlant: Intercepted water at the vegetation [mm]
             IntWalltot: Total Intercepted water [mm]
        WB: Water balance (it should be close to zero)
            dIn_veg_dt: Water storage at the vegetation [mm s^-1]
            WBalance_veg_tot: Water balance for the vegetated surface [mm s^-1]
            Total: Total water balance [mm s^-1]
        Run:
            RunonWallTot: Total runon [mm s^-1]
            RunoffWallTot: Total runoff [mm s^-1]
            QWallImp : Runoff from impervious wall [mm s^-1]
            QWallVeg : Runoff from vegetation (Summation of dripping, saturation excess, and throughfall) [mm s^-1]
            Anthp: Anthropogenic water [mm s^-1]
        Owater_OwWallSoilVeg: Water content (soil moisture) in each layer [-]
        """

        Water_Cal = Water_Calculations()

        Runon_tm1 = copy.copy(self.Run.RunonWallTot)

        Ewall_imp = 0
        self.Int.IntWallImp = 0
        Sp_In = 0.2
        LAI = 3
        SAI = 0.001
        # Vegetation
        # Impervious wall
        q_runoff_imp, self.Int.IntWallImp, dIn_imp_dt, Lk_imp, WBalance_In_imp = \
            Water_Cal.Water_Impervious(MeteoData.Rain, Runon_tm1, Ewall_imp, self.Int.IntWallImp,ParCalculation.dts,ParCalculation.rhow,
                                       0,0)
        # Vegetation
        q_runoff_veg, self.Int.IntWallVegPlant, dIn_veg_dt, WBalance_In_veg = \
            Water_Cal.Water_Vegetation(MeteoData.Rain,Ewall_veg,self.Int.IntWallVegPlant,Sp_In,LAI,
                                       SAI,ParCalculation.rhow,ParCalculation.dts)
        
        # Infiltration rate for the soil of vegetated wall [mm s^-1]
        f_wallvegsoil = 2e-3

        # Soil column
        V, self.Owater_OwWallSoilVeg, OSwWallSoil, Lk, _Psi_s_H_, Psi_s, _Exwat_H_, Exwat, Rd, self.TEfluxWallVeg, _TE_H_, \
        self.EfluxWallVegSoil, dV_dt, WBalance_soil, Psi_soil, Ko = \
            Water_Cal.Water_Soil(self.Owater_OwWallSoilVeg, f_wallvegsoil, TEfluxWallVeg_EB, TEfluxWallVeg_EB, EfluxWallVegSoil_EB,
                                 [0.*ParSoilWall.Zs[i] for i in range(len(ParSoilWall.Zs))],ParCalculation.dts,ParSoilWall.Pcla,
                                 ParSoilWall.Psan,ParSoilWall.Porg,ParSoilWall.Kfc,ParSoilWall.Phy,ParSoilWall.SPAR,ParSoilWall.Kbot,
                                 ParVegWall.CASE_ROOT,ParVegWall.CASE_ROOT,ParVegWall.ZR95,ParVegWall.ZR95,ParVegWall.ZR50,ParVegWall.ZR50,ParVegWall.ZRmax,ParVegWall.ZRmax,
                                 ParVegWall.Rrootl,ParVegWall.Rrootl,ParVegWall.PsiL50,ParVegWall.PsiL50,ParVegWall.PsiX50,ParVegWall.PsiX50,ParSoilWall.Zs,ParCalculation.rhow)

        # Calculate total runoff as the fraction of total excess water that leaves the system [mm s^-1]
        self.Run.RunonWallTot = FractionsWall.Per_runoff * (FractionsWall.fimp*q_runoff_imp + FractionsWall.fveg*q_runoff_veg)
        # Set runon of wall as zero
        self.Run.RunoffWallTot = 0


        # Water balance for the impervious surface [mm s^-1]
        WBalance_imp_tot = MeteoData.Rain + Runon_tm1 - Ewall_imp*1000/ParCalculation.rhow - q_runoff_imp - dIn_imp_dt
        # Water balance for the vegetated surface [mm s^-1]
        WBalance_veg_tot = MeteoData.Rain + Runon_tm1 + Anthropogenic.Waterf_wall/3600 - \
                           (Ewall_veg + self.EfluxWallVegSoil + self.TEfluxWallVeg) * 1000 / ParCalculation.rhow - dIn_veg_dt - q_runoff_veg

        # Calculate total water evaporated [mm s^-1]
        E_tot = (FractionsWall.fimp*Ewall_imp + FractionsWall.fveg*(Ewall_veg + self.EfluxWallVegSoil + self.TEfluxWallVeg))*1000/ParCalculation.rhow
        # Calculate total storage [mm s^-1]
        Storage_tot = FractionsWall.fimp*dIn_imp_dt + FractionsWall.fveg*dIn_veg_dt

        # Calculate total water balance [mm s^-1]
        WBalance_tot = MeteoData.Rain + Runon_tm1 + FractionsWall.fveg*Anthropogenic.Waterf_wall/3600 - E_tot - \
                       self.Run.RunoffWallTot - self.Run.RunonWallTot - Storage_tot

        self.Run.QWallImp = q_runoff_imp
        self.Run.QWallVeg = q_runoff_veg
        self.Run.QWallVegSoil = Rd

        self.dInt_dt.dInt_dtWallVegPlant = dIn_veg_dt
        self.dInt_dt.dInt_dtWalltot = self.dInt_dt.dInt_dtWallVegPlant

        self.Anthp = Anthropogenic.Waterf_wall/3600

        self.ExWaterWall_L = Exwat
        self.VWallSoil = V
        self.SoilPotWWall_L = Psi_s

        self.WB.In_veg = WBalance_In_veg
        self.WB.imp_tot = WBalance_imp_tot
        self.WB.veg_tot = WBalance_veg_tot
        self.WB.soil = WBalance_soil
        self.WB.Total = WBalance_tot

        self.Int.IntWalltot = self.Int.IntWallVegPlant