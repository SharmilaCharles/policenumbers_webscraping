from pydantic import BaseModel, Field

class DistrictOfficer(BaseModel):
    officer_name: str = Field(description="Name of the officer (Handle 'Vacant' if no name is provided)")
    district_name: str | None = Field(default=None, description="Name of the District or City")
    contact_number: str | None = Field(default=None, description="Contact number (mobile or landline) of the officer")
    email: str | None = Field(default=None, description="Official email address")

class PoliceStation(BaseModel):
    station_name: str = Field(description="Name of the Police Station")
    officer_name: str = Field(description="Name of the officer (e.g., Inspector of Police)")
    landline_number: str | None = Field(default=None, description="Landline number of the police station")
    mobile_number: str | None = Field(default=None, description="Mobile number of the station officer")
    email: str | None = Field(default=None, description="Official email address of the police station")

class District(BaseModel):
    district_name: str = Field(description="Name of the District or City Police")
    
    # --- DISTRICT OFFICERS ---
    sp: list[DistrictOfficer] = Field(default_factory=list, description="SUPERINTENDENT OF POLICE - SP")
    adsp: list[DistrictOfficer] = Field(default_factory=list, description="ADDITIONAL SUPERINTENDENT OF POLICE - ADSP")
    dsp: list[DistrictOfficer] = Field(default_factory=list, description="DEPUTY SUPERINTENDENT OF POLICE - DSP")
    
    # --- CITY OFFICERS ---
    cop: list[DistrictOfficer] = Field(default_factory=list, description="COMMISSIONER OF POLICE - COP")
    acop: list[DistrictOfficer] = Field(default_factory=list, description="ADDITIONAL COMMISSIONER OF POLICE - ACOP")
    jcp: list[DistrictOfficer] = Field(default_factory=list, description="JOINT COMMISSIONER OF POLICE - JCP")
    dcp: list[DistrictOfficer] = Field(default_factory=list, description="DEPUTY COMMISSIONER OF POLICE - DCP")
    adc: list[DistrictOfficer] = Field(default_factory=list, description="ADDITIONAL DEPUTY COMMISSIONER OF POLICE - ADC")
    acp: list[DistrictOfficer] = Field(default_factory=list, description="ASSISTANT COMMISSIONER OF POLICE - ACP")
    
    # --- STATIONS ---
    police_stations: list[PoliceStation] = Field(default_factory=list, description="List of all police stations")