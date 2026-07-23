<?xml version="1.0" encoding="UTF-8"?>
<!-- benefits_carrier_file.xsl: Get_Benefit_Enrollments -> 834-style carrier CSV -->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wd="urn:com.workday/bsvc" exclude-result-prefixes="env wd">
  <xsl:output method="text"/>
  <xsl:template match="/">
    <xsl:text>SUBSCRIBER_ID,LAST_NAME,FIRST_NAME,PLAN,COVERAGE_LEVEL,EE_COST&#10;</xsl:text>
    <xsl:for-each select="//wd:Worker_Benefit_Data">
      <xsl:variable name="emp" select="wd:Worker_Reference/wd:ID"/>
      <xsl:variable name="ln" select="wd:Last_Name"/>
      <xsl:variable name="fn" select="wd:First_Name"/>
      <xsl:for-each select="wd:Enrollment">
        <xsl:value-of select="concat($emp,',',$ln,',',$fn,',',wd:Benefit_Plan,',',wd:Coverage_Level,',',wd:Employee_Cost,'&#10;')"/>
      </xsl:for-each>
    </xsl:for-each>
  </xsl:template>
</xsl:stylesheet>
