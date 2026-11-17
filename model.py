from pydantic import BaseModel, Field
from typing import List, Optional

class DistrictOfficer(BaseModel):
    officer_name: str = Field(description="Name of the officer (Handle 'Vacant' if no name is provided)")
    contact_number: Optional[str] = Field(default=None, description="Contact number (mobile or landline) of the officer")
    email: Optional[str] = Field(default=None, description="Official email address")

class PoliceStation(BaseModel):
    station_name: str = Field(description="Name of the Police Station")
    officer_name: str = Field(description="Name of the officer (e.g., Inspector of Police)")
    landline_number: Optional[str] = Field(default=None, description="Landline number of the police station")
    mobile_number: Optional[str] = Field(default=None, description="Mobile number of the station officer")
    email: Optional[str] = Field(default=None, description="Official email address of the police station")

class District(BaseModel):
    district_name: str = Field(description="Name of the District or City Police")
    superintendents: List[DistrictOfficer] = Field(description="List of SUPERINTENDENT OF POLICE (SP) for the district")
    additional_superintendents: List[DistrictOfficer] = Field(description="List of ADDITIONAL SUPERINTENDENT OF POLICE (ADSP)")
    deputy_superintendents: List[DistrictOfficer] = Field(description="List of DEPUTY SUPERINTENDENT OF POLICE (DSP)")
    police_stations: List[PoliceStation] = Field(description="List of all police stations listed under this district")

class DistrictContacts(BaseModel):
    districts: List[District]