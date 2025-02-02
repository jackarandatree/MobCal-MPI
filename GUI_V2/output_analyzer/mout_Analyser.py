import os
import re
import numpy as np
from math import factorial
from scipy.optimize import curve_fit
from scipy.stats import gaussian_kde
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams.update({'font.size': 12})
matplotlib.rcParams.update({'lines.linewidth': 1.5})
#from PyQt5.QtWidgets import QMessageBox

class mout_info:
    '''class with all info and functions from mout files'''
    def __init__(self,directory,file):
        '''reading in all data from the mout file and storing them in arrays'''
        opf = open(directory+file,'r')
        data = opf.read()
        opf.close()
        
        # constants without self.
        elC = 1.60217733E-19 # C
        kB = 1.380658E-23 # J/K
        amu2kg = 1.660539e-27 #amu/kg
        # constants with self.
        eo, ro = re.findall('van der Waals scaling parameters: eo= (.*?)eV, ro= (.*?)A', data)[0]
        self.ro = float(ro) # angstrom
        self.eo = float(eo) # eV
        self.piro2 = np.pi*(self.ro)**2 # Q = piro2 * Qst
        self.Tfac = kB/(self.eo*elC) # Tst = Tfac * T
        
        coll_mass = {"He": 4.0026, "N2": 28.0062}
        
        self.direc = directory
        self.filename = re.findall('input file name = (.*?)\n',data)[0].strip()[:-4]
        
        #get atom mass
        try:
            self.mass = float(re.findall('mass of ion = (.*?)\n',data)[0].replace('D','E').replace('amu','').strip())
        except:
            self.mass = 0.00
        
        #get collision gas
        try:
            self.coll_gas = re.findall('Mobility Calculated under (.*?) gas',data)[0].strip()
        except:
            self.coll_gas = 'N2'
        
        #compute reduced mass:
        self.redmass = coll_mass[self.coll_gas]*self.mass / (coll_mass[self.coll_gas]+self.mass)
        self.gfac = np.sqrt( (self.eo*elC) / (0.5*self.redmass*amu2kg) ) # g = gfac * gst
        
        #get number of atoms
        try:
            self.Natoms = int(re.findall('number of atoms = (.*?)\n',data)[0].strip())
        except:
            self.Natoms = 0
        
        #get NTgrid
        try:
            self.NTgrid = int(re.findall('# of T_eff grid points = (.*?)\n',data)[0].strip())+1
        except:
            self.NTgrid = 1
        
        #get empirical correction data
        if 'Empirical correction turned off' in data:
            self.EmpCorr = False
            self.EmpCorr_A = 0.
            self.EmpCorr_B = 0.
        else:
            self.EmpCorr = True
            self.EmpCorr_A = float(re.findall('A =   (.*?)\n',data)[0].strip())
            self.EmpCorr_B = float(re.findall('B = (.*?) Td\n',data)[0].strip())
        
        #get integration parameters
        try:
            self.itn = int(re.findall('number of complete cycles (.*?)\n', data)[0].rsplit(' ')[-1].strip())
            self.inp = int(re.findall('number of velocity points (.*?)\n', data)[0].rsplit(' ')[-1].strip())
            self.imp = int(re.findall('number of random points (.*?)\n', data)[0].rsplit(' ')[-1].strip())
        except:
            print('Problems reading itn, inp, imp')
        
        # momentum transfer data
        # gst q1st +/- q1st_err q2st +/- q2st_err q3st +/- q3st_err
        try:
            ifind = data.find('Final averaged values of Q*(l):')
            MT_str = ((data[ifind:ifind+112+self.inp*88]).replace('+/-','').split('\n')[3:])
            MT_arr = np.array([[float(s) for s in MT_str_line.split()] for MT_str_line in MT_str])
            if MT_arr.shape[0] != self.inp:
                print('not all MT data read in!')
            self.gst      = MT_arr[:,0]       # velocity grid
            self.qist     = MT_arr[:,[1,3,5]] # Q^(l), l=1,2,3
            self.qist_err = MT_arr[:,[2,4,6]] # sig(Q^(l)), l=1,2,3
        except:
            raise ValueError('Could not retrieve momentum transfer data. Job not finished!')
        
        # mobility summary
        # Teff [K]   E/N [Td]  K0 [cm**2/Vs]  CCS [A**2]  uncertainty
        try:
            mob_str = ((data[data.find('Mobility Summary')+25:]).replace('%','').split('\n')[4:-3])
            mob_arr = np.array([[float(s) for s in mob_str_line.split()] for mob_str_line in mob_str])
            self.Teff_r   = mob_arr[:,0]
            self.EN_r     = mob_arr[:,1]
            self.K0_r     = mob_arr[:,2]
            self.CCS_r    = mob_arr[:,3]
            self.uncert_r = mob_arr[:,4] # in percent!
            self.alpha_func = self.K0_r/self.K0_r[0] - 1.
            
            # check if there are more than just low-field data
            if len(self.Teff_r) > 1:
                self.highfield = True
            else:
                self.highfield = False
        except:
            raise ValueError('Could not retrieve Mobility Summary. Job not finished!')
        
        # get calculation time
        try:
            time = float(re.findall('Job Completed in(.*?)\n',data)[0].strip().replace('s',''))
            self.time = str(round(time,2))
        except:
            self.time = 0.0
        
        # make a summary text to be printed in the GUI
        stext = []
        stext.append(self.filename.rsplit('.')[0])
        stext.append('')
        stext.append('itn=%i, inp=%i, imp=%i' %(self.itn, self.inp, self.imp))
        stext.append('Collision gas: %s' %self.coll_gas)
        stext.append('Empirical Correction: %s' %(self.EmpCorr))
        stext.append('')
        stext.append('T_bath set to %.0f K' %(self.Teff_r[0]))
        stext.append('CCS(T_bath) = %6.1f +/- %5.1f Ang^2' %(self.CCS_r[0], 1e-2*self.CCS_r[0]*self.uncert_r[0]))
        stext.append('K0( E/N=0 ) = %6.3f +/- %5.3f cm^2/Vs' %(self.K0_r[0], 1e-2*self.K0_r[0]*self.uncert_r[0]))
        stext.append('')
        if self.highfield:
            stext.append('CCS      calculated up to %4.0f K' %(self.Teff_r[-1]))
            stext.append('Mobility calculated up to %4.1f Td' %(self.EN_r[-1]))
        
        self.summary_text = stext
    
    # function to calculate OM^(l,s) at Teff on the fly.
    # will be called from a button so maybe not necessary to check validity of input?
    def OM(self,l,s,Teff):
        '''Computes collision integral OM^(l,s) and its error at Teff (K) in Ang**2. l=1-3, s=1-4'''
        if Teff<self.Teff_r.min() or Teff>self.Teff_r.max():
            raise ValueError('Teff out of range! Must be between %.0f and %.0f K' %(self.Teff_r.min(),self.Teff_r.max()))
        
        Tst = Teff*self.Tfac
        dgst = self.gst[1] - self.gst[0]
        w = 2./( factorial(s+1)*Tst**(s+2)) * self.gst**(2*s+3) * np.exp(-self.gst**2/Tst)
        q = self.qist[:,l-1]
        qerr = self.qist_err[:,l-1]
        # integrate
        I = np.sum(w*q*dgst) * self.piro2
        Ierr = np.sqrt(np.sum((w*qerr*dgst)**2)) * self.piro2
        
        return I, Ierr
    
    # function to calculate and plot the alpha function and coefficients
    # again, input check not necessary since order N is chosen from dropdown box
    def get_alpha_coeff(self,nord=6,plotting=False):
        '''Express K(E/N) = K(0)*[1 + a2*(E/N)^2 + a4*(E/N)^4 + ...]
        and get a2 in 1/Td^2 and a4 in 1/Td^4. nord is either 4 or 6'''
        K0_SI = self.K0_r * 1e-4 # in m^2/Vs
        
        # check order or approx (nord=4 or =6)
        if nord == 4:
            fit = lambda x, a2, a4: K0_SI[0]*(1. + a2*x**2 + a4*x**4)
        elif nord == 6:
            fit = lambda x, a2, a4, a6: K0_SI[0]*(1. + a2*x**2 + a4*x**4 + a6*x**6)
        else:
            raise ValueError('nord must be 4 or 6')
        
        # fit to function
        popt, pcov = curve_fit(fit, self.EN_r, K0_SI)
        
        if plotting:
            # alpha coeff label for plot
            al_lab = ''
            for i in range(nord//2):
                a_exp = np.floor(np.log10(np.abs(popt[i]))) # round to next lower integer (also when negative!)
                a_pre = popt[i]/(10**a_exp) # prefactor of exponent
                al_lab += r'$\alpha_{%i}$ = $%+.4f\times10^{%i}$ Td$^{-%i}$'%(2*(i+1),a_pre,a_exp,2*(i+1))
                al_lab += '\n'
            
            # plot for visualization
            plt.figure()
            plt.plot(self.EN_r, self.K0_r, 'kx-', label='MobCal-MPI data')
            plt.plot(self.EN_r, 1e4*fit(self.EN_r, *popt), 'r--', label=al_lab)
            plt.legend()
            plt.xlabel(r'$E/N$ [Td]')
            plt.ylabel(r'$K_0$ [cm$^2$/Vs]')
            plt.tight_layout()
            plt.show()
        
        return popt
    
    ## exporting functions
    def export_CCS(self):
        '''writes the CCS data to a file'''
        X = np.vstack([self.Teff_r, self.CCS_r, self.CCS_r*self.uncert_r*1e-2]).T
        
        fo = open(self.direc+self.filename+'_CCSdata.csv','w')
        fo.write('Teff [K],  CCS [A**2],  errCCS [A**2] \n')
        for Xi in X:
            fo.write(' %7.2f,   %7.2f,      %5.2f' %(*Xi,) + '\n')
        fo.close()
    
    def export_Ql(self):
        '''writes the momentum transfer data to a file'''
        g = self.gfac * self.gst
        Ql = self.qist * self.piro2
        sigQl = self.qist_err * self.piro2
        X = np.vstack([g, Ql[:,0], sigQl[:,0], Ql[:,1], sigQl[:,1], Ql[:,2], sigQl[:,2]]).T
        
        fo = open(self.direc+self.filename+'_MTdata.csv','w')
        fo.write('g [m/s],  Q(1) [A**2],  errQ(1) [A**2],  Q(2) [A**2],  errQ(2) [A**2],  Q(3) [A**2],  errQ(3) [A**2] \n')
        for Xi in X:
            fo.write('%6.1f,     %6.2f,        %6.2f,         %6.2f,        %6.2f,         %6.2f,        %6.2f' %(*Xi,) + '\n')
        fo.close()
    
    def export_K(self):
        '''writes the mobility data to a file'''
        #a2, a4, a6 = self.get_alpha_coeff(nord=6, plotting=False)
        #alpha_fit = a2*self.EN_r**2 + a4*self.EN_r**4 + a6*self.EN_r**6
        
        X = np.vstack([self.EN_r, self.K0_r, self.alpha_func]).T
        
        fo = open(self.direc+self.filename+'_Mobidata.csv','w')
        fo.write('E/N [Td],  K0 [cm2/Vs],  alpha func\n')
        for Xi in X:
            fo.write(' %6.2f,     %6.4f,      %+6.4f' %(*Xi,) + '\n')
        fo.close()
    
    def export_summary(self):
        '''writes the summary table at the end of the .mout file to a new file'''
        X = np.vstack([self.Teff_r, self.EN_r, self.K0_r, self.CCS_r, self.uncert_r]).T
        
        fo = open(self.direc+self.filename+'_summary.csv','w')
        fo.write(' Teff [K],  E/N [Td], K0 [cm**2/Vs], CCS [A**2], uncertainty\n')
        for Xi in X:
            fo.write(' %7.2f,    %6.2f,      %6.4f,     %7.2f,     %5.2f' %(*Xi,) + '%\n')
        fo.close()

    ## purely plotting functions
    def plot_CCS(self):
        '''Plotting CCS over the available Teff range'''
        plt.figure(figsize=(4,3),dpi=250)
        plt.plot(self.Teff_r,self.CCS_r)
        plt.fill_between(self.Teff_r,self.CCS_r*(1.+self.uncert_r*1e-2),
                             self.CCS_r*(1.-self.uncert_r*1e-2),color='C0',alpha=0.3)
        plt.xlabel(r'$T_{eff}$ [K]')
        plt.ylabel(r'CCS [$\AA^2$]')
        plt.tight_layout()
        plt.show()
    
    def plot_CCS_integrand(self):
        '''Plotting CCS integrand over the velocity range'''
        g = self.gfac * self.gst
        Tst = self.Teff_r[0]*self.Tfac # T_bath in T*
        l,s = 1,1
        w = 2./( factorial(s+1)*Tst**(s+2)) * self.gst**(2*s+3) * np.exp(-self.gst**2/Tst)
        Iy = self.qist[:,l-1]*w
        Iyerr = self.qist_err[:,l-1]*w
        plt.figure(figsize=(4,3),dpi=250)
        plt.plot(g,Iy,color='cornflowerblue',label=r'%.1f $\pm$ %.1f $\AA^2$' %(self.CCS_r[0], self.CCS_r[0]*self.uncert_r[0]*1e-2) )
        plt.fill_between(g,Iy+Iyerr,Iy-Iyerr,color='cornflowerblue',alpha=0.3)
        plt.xlabel(r'$g$ [m/s]')
        plt.ylabel(r'CCS Integrand [a.u.]')
        plt.legend()
        plt.yticks([])
        plt.tight_layout()
        plt.show()
    
    def plot_Qldat(self,lmax=3):
        '''Plots momentum transfer integrals Q^(l) up to lmax = 1,2 or 3.'''
        g = self.gfac * self.gst
        plt.figure(figsize=(4,3),dpi=250)
        for l in range(lmax): # l is actually l-1
            plt.plot(g,self.qist[:,l]*self.piro2,'C%i'%l,label=r'$l=%i$'%(l+1))
            plt.fill_between(g,(self.qist[:,l]+self.qist_err[:,l])*self.piro2,
                             (self.qist[:,l]-self.qist_err[:,l])*self.piro2,
                             color='C%i'%l,alpha=0.3)
        plt.ylabel(r'$Q^{(l)}$ [$\AA^2$]')
        plt.xlabel(r'$g$ [m/s]')
        plt.legend()
        plt.grid(which='both',lw=0.3)
        plt.tight_layout()
        # plt.savefig(self.directory+self.basen+'_Ql.png', dpi=400,
        #             format='png', bbox_inches='tight')
        # print('Momentum Transfer Cross Section plot saved to %s' %self.directory)
        plt.show()

class many_mout:
    def __init__(self,direc):
        self.direc = direc
        
        self.files = [x.rsplit('.',1)[0] for x in os.listdir(self.direc) if x.lower().endswith('.mout')]
        self.M_list = [mout_info(self.direc, file+'.mout') for file in self.files]
        self.Nfiles = len(self.files)
        self.maxlen_fname = np.max([len(file) for file in self.files])
        
        # make a summary text to be printed in the GUI
        stext = []
        stext.append('%i files read in' %self.Nfiles)
        
        # see if T_bath is the same
        Tbath_list = [int(M.Teff_r[0]) for M in self.M_list]
        if all(Tbath_list[0] == T for T in Tbath_list):
            stext.append('common Tbath: %i K' %Tbath_list[0])
            self.common_Tbath = True
        else:
            stext.append('Tbath ranges from %.0f to %0.f K' %(np.min(Tbath_list),np.max(Tbath_list)))
            self.common_Tbath = False
        stext.append('')
        
        # check low/high field data
        if all([M.highfield==True for M in self.M_list]):
            stext.append('All files contain high field data')
            self.dat_type = 'highfield' # all mout files contain high field data
        elif all([M.highfield==False for M in self.M_list]):
            stext.append('All files contain low field data only')
            self.dat_type = 'lowfield' # all mout files contain only low field data
        else:
            stext.append('Mixed high and low field data files!')
            stext.append('Only low field data can be exported!')
            self.dat_type = 'mixed' # some mout files have only low, some only high field data
        stext.append('')
        
        # all filenames with low field CCS and K0
        stext.append('filename' + ' '*(self.maxlen_fname-8) +' CCS [Ang**2]  K0 [cm2/Vs]')
        for M in self.M_list:
            stext.append("{0:<{1}}".format(M.filename, self.maxlen_fname) + '   %7.2f       %6.4f' %(M.CCS_r[0],M.K0_r[0]))
        self.summary_text = stext
    
    def plot_CCS_list(self):
        '''plots all low field CCSs of M_list in a bar plot'''
        xpos = np.arange(self.Nfiles)
        CCSs = [M.CCS_r[0] for M in self.M_list]
        labels = [M.filename for M in self.M_list]
        
        plt.figure()
        h = plt.bar(xpos,CCSs)
        plt.subplots_adjust(bottom=0.3)
        xticks_pos = [0.65*patch.get_width() + patch.get_xy()[0] for patch in h]
        _ = plt.xticks(xticks_pos, labels, ha='right', rotation=45)
        plt.ylabel(r'CCS / $\AA^2$')
        plt.show()
    
    def plot_CCS_dist(self):
        '''plots the distribution (histogram) of all low field CCSs of M_list'''
        CCSs = [M.CCS_r[0] for M in self.M_list]
        minCCS = np.min(CCSs)
        maxCCS = np.max(CCSs)
        #bins = np.arange(int(minCCS),int(maxCCS)+1,self.Nfiles//100+1)
        kde = gaussian_kde(CCSs)
        xCCS = np.linspace(minCCS*0.9,maxCCS*1.1,201)
        #avg_CCS = np.mean(CCSs)
        
        plt.figure()
        plt.hist(CCSs,bins=30,density=True,alpha=0.3,color='C0',label='histogram')
        plt.plot(xCCS,kde(xCCS),'C0-',label='Gaussian smooth')
        #plt.vlines(avg_CCS,0,kde(avg_CCS)*1.1,color='r')
        #plt.text(avg_CCS,kde(avg_CCS)*1.1,'avg. = %.1f $\AA^2$' %avg_CCS)
        plt.xlabel(r'CCS / $\AA^2$')
        plt.ylabel('frequency')
        plt.legend(loc='upper right')
        plt.show()
    
    def export_CCS(self,itype=0):
        if self.common_Tbath:
            Tinfo = '# All CCS calculated at Tbath = %.1f K\n' %(self.M_list[0].Teff_r[0])
        else:
            Tinfo = '# WARNING: CCSs calculated at different Tbaths!\n'
        
        # export low field data
        if itype == 0:
        #if self.dat_type == 'lowfield' or self.dat_type == 'mixed':
            CCSs = [M.CCS_r[0] for M in self.M_list]
            errCCSs = [M.CCS_r[0]*M.uncert_r[0]*1e-2 for M in self.M_list]
            
            fo = open(self.direc+'Export_mout_CCS_lowfield.csv','w')
            fo.write(Tinfo)
            fo.write('filename' + ' '*(self.maxlen_fname-8) +', CCS [A**2],  errCCS [A**2] \n')
            for i in range(self.Nfiles):
                fo.write("{0:<{1}}".format(self.files[i], self.maxlen_fname) +  ', %7.2f   ,   %5.2f' %(CCSs[i],errCCSs[i]) + '\n')
        
        # export high field data
        else:
        #elif self.dat_type == 'highfield':
            Teffs = [M.Teff_r for M in self.M_list]
            # check if all Teffs are compatible
            TF_set = [ all( Teff_i == Teffs[0] ) for Teff_i in Teffs ]
            if all(TF_set):
                Tgrid_info = '# All CCS calculated on same Teff grid\n'
                Teff_grid = Teffs[0]
                Ngrid = len(Teff_grid)
                CCSs = np.array([M.CCS_r for M in self.M_list])
            else:
                Tgrid_info = '# WARNING: Teff grids not matching. Interpolation on common range used!\n'
                Ngrid = np.max([len(M.CCS_r) for M in self.M_list])
                common_Tmin = np.max(np.min(Teffs,axis=1))
                common_Tmax = np.min(np.max(Teffs,axis=1))
                Teff_grid = np.linspace(common_Tmin,common_Tmax,Ngrid)
                CCSs = np.array([ interp1d(M.Teff_r,M.CCS_r)(Teff_grid) for M in self.M_list ])
            
            fo = open(self.direc+'Export_mout_CCS_highfield.csv','w')
            fo.write(Tinfo)
            fo.write(Tgrid_info)
            
            # files in columns
            fo.write('Teff(K) \ CCS(A^2) of' + ', %s'*self.Nfiles %(*self.files,) +'\n')
            for i in range(Ngrid):
                fo.write('%7.2f              '%Teff_grid[i] + ', %7.2f'*self.Nfiles %(*CCSs[:,i],) + '\n')
            
            # files in rows
            # N1r = np.max([21,self.maxlen_fname])
            # fo.write('filename \ CCS at T/K' + ' '*(N1r-21) +', %6.1f '*Ngrid %(*Teff_grid,) +'\n')
            # for i in range(self.Nfiles):
            #     fo.write("{0:<{1}}".format(self.files[i], N1r) + ', %7.2f'*Ngrid %(*CCSs[i],) + '\n')
        
        fo.close()
    
    def export_Mobility(self,itype=0):
        if self.common_Tbath:
            Tinfo = '# All mobility data calculated at Tbath = %.1f K\n' %(self.M_list[0].Teff_r[0])
        else:
            Tinfo = '# WARNING: mobility data calculated at different Tbaths!\n'
        
        # export low field data
        if itype == 0:
        #if self.dat_type == 'lowfield' or self.dat_type == 'mixed':
            K0s = [M.K0_r[0] for M in self.M_list]
            errK0s = [M.K0_r[0]*M.uncert_r[0]*1e-2 for M in self.M_list]
            
            fo = open(self.direc+'Export_mout_K0_lowfield.csv','w')
            fo.write(Tinfo)
            fo.write('filename' + ' '*(self.maxlen_fname-8) +', K0 [cm2/Vs],  errK0 [cm2/Vs]\n')
            for i in range(self.Nfiles):
                fo.write("{0:<{1}}".format(self.files[i], self.maxlen_fname) +  ',   %6.4f   ,      %6.4f' %(K0s[i],errK0s[i]) + '\n')
        
        # export high field data
        else:
        #elif self.dat_type == 'highfield':
            Ngrid = np.max([len(M.CCS_r) for M in self.M_list])
            EN_max = np.min(np.max([M.EN_r for M in self.M_list],axis=1)) # common maximum E/N
            common_EN = np.linspace(0.,EN_max,Ngrid) # common E/N grid
            K0_ips = np.array([ interp1d(M.EN_r, M.K0_r)(common_EN) for M in self.M_list ]) # interpolate K0 data on common E/N grid
            
            fo = open(self.direc+'Export_mout_K0_highfield.csv','w')
            fo.write(Tinfo)
            fo.write('E/N(Td) \ K0(cm^2/Vs) of' + ', %s'*self.Nfiles %(*self.files,) +'\n')
            for i in range(Ngrid):
                fo.write('%6.2f'%common_EN[i] + ' '*(24-6) + ', %6.4f'*self.Nfiles %(*K0_ips[:,i],) + '\n')
        
        fo.close()