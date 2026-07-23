<?xml version="1.0" encoding="UTF-8"?>
<!-- workers_to_psv.xsl
     Transforms Get_Workers_Response into a pipe-delimited file.
     Same pattern as a Studio/EIB outbound transform. -->
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wd="urn:com.workday/bsvc"
    exclude-result-prefixes="env wd">

  <xsl:output method="text" encoding="UTF-8"/>

  <xsl:template match="/">
    <!-- Header row -->
    <xsl:text>EMPLOYEE_ID|FIRST_NAME|LAST_NAME|EMAIL|HIRE_DATE|ORG|STATUS&#10;</xsl:text>
    <xsl:apply-templates select="//wd:Worker"/>
  </xsl:template>

  <xsl:template match="wd:Worker">
    <xsl:value-of select="wd:Worker_Data/wd:Worker_ID"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="wd:Worker_Data/wd:Personal_Data/wd:Name_Data/wd:Legal_Name_Data/wd:Name_Detail_Data/wd:First_Name"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="wd:Worker_Data/wd:Personal_Data/wd:Name_Data/wd:Legal_Name_Data/wd:Name_Detail_Data/wd:Last_Name"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="wd:Worker_Data/wd:Personal_Data/wd:Contact_Data/wd:Email_Address_Data/wd:Email_Address"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="wd:Worker_Data/wd:Employment_Data/wd:Worker_Status_Data/wd:Hire_Date"/>
    <xsl:text>|</xsl:text>
    <xsl:value-of select="wd:Worker_Data/wd:Organization_Data/wd:Organization_Name"/>
    <xsl:text>|</xsl:text>
    <xsl:choose>
      <xsl:when test="wd:Worker_Data/wd:Employment_Data/wd:Worker_Status_Data/wd:Active = '1'">ACTIVE</xsl:when>
      <xsl:otherwise>TERMINATED</xsl:otherwise>
    </xsl:choose>
    <xsl:text>&#10;</xsl:text>
  </xsl:template>

</xsl:stylesheet>
