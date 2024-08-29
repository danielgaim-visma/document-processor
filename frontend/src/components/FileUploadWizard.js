import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { ArrowRight, Upload, Bot, Download, CheckCircle, Loader, X } from 'lucide-react';
import { useDropzone } from 'react-dropzone';
import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from '../components/ui/tooltip';
import { Progress } from '../components/ui/progress';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Button } from '../components/ui/button';

import { API_BASE_URL } from '../utils/apiConfig';

console.log('API_BASE_URL:', API_BASE_URL);

const FileUploadWizard = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [file, setFile] = useState(null);
  const [parsedSections, setParsedSections] = useState(null);
  const [keywords, setKeywords] = useState([]);
  const [zipFilename, setZipFilename] = useState(null);
  const [error, setError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processedSections, setProcessedSections] = useState(0);
  const [totalSections, setTotalSections] = useState(0);

  const steps = useMemo(() => [
    { name: 'Last opp fil', icon: Upload, description: 'Velg og last opp dokumentet ditt' },
    { name: 'Behandle seksjoner', icon: Bot, description: 'AI behandler og analyserer dokumentet' },
    { name: 'Last ned ZIP', icon: Download, description: 'Få dine behandlede filer' },
    { name: 'Fullført', icon: CheckCircle, description: 'Prosessen er fullført' }
  ], []);

  const MAX_FILE_SIZE = useMemo(() => 10 * 1024 * 1024, []); // 10MB

  const ALLOWED_FILE_TYPES = useMemo(() => [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ], []);

  const testServerConnection = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/`);
      const data = await response.text();
      console.log("Resultat av servertilkoblingstest:", data);
    } catch (error) {
      console.error("Servertilkoblingstest mislyktes:", error);
    }
  }, []);

  useEffect(() => {
    testServerConnection();
  }, [testServerConnection]);

  const onDrop = useCallback((acceptedFiles) => {
    const file = acceptedFiles[0];
    if (file.size > MAX_FILE_SIZE) {
      setError('Filstørrelsen overskrider grensen på 10MB');
      return;
    }
    if (!ALLOWED_FILE_TYPES.includes(file.type)) {
      setError('Ugyldig filtype. Vennligst last opp en PDF, Word-dokument, tekstfil eller Excel-ark.');
      return;
    }
    setFile(file);
    setError(null);
  }, [MAX_FILE_SIZE, ALLOWED_FILE_TYPES]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

  const handleUploadAndParse = async () => {
    if (!file) return;

    setIsUploading(true);
    setError(null);
    const formData = new FormData();
    formData.append('file', file);

    try {
      console.log("Sender forespørsel til server...");
      console.log("Forespørsels-URL:", `${API_BASE_URL}/api/upload-and-parse`);
      console.log("Fil som sendes:", file);

      const response = await fetch(`${API_BASE_URL}/api/upload-and-parse`, {
        method: 'POST',
        body: formData,
        mode: 'cors',
      });

      console.log("Svar mottatt:", response);

      if (response.ok) {
        const data = await response.json();
        console.log("Analyserte data:", data);
        setParsedSections(data.parsed_sections);
        setKeywords(data.keywords);
        setCurrentStep(1);
      } else {
        const errorText = await response.text();
        console.error('Serveren svarte med en feil:', response.status, errorText);
        setError(`Filopplasting og analysering mislyktes: ${errorText} (Status: ${response.status})`);
      }
    } catch (error) {
      console.error('Nettverksfeil:', error);
      setError(`Nettverksfeil under filopplasting og analysering: ${error.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleProcessSections = async () => {
    setIsProcessing(true);
    setError(null);
    setProcessedSections(1);  // Start at 1 instead of 0
    setTotalSections(parsedSections.length);
    try {
      const response = await fetch(`${API_BASE_URL}/api/process-sections`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          parsed_sections: parsedSections,
          keywords: keywords,
          original_filename: file.name
        }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line);
              if (data.progress) {
                setProcessedSections(data.progress);
              } else if (data.zip_file) {
                setZipFilename(data.zip_file);
                setCurrentStep(2);
              } else if (data.error) {
                throw new Error(data.error);
              }
            } catch (parseError) {
              console.error('Error parsing server response:', parseError);
            }
          }
        }
      }
    } catch (error) {
      console.error('Feil ved behandling av seksjoner:', error);
      setError(`Feil ved behandling av seksjoner: ${error.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownload = () => {
    if (zipFilename) {
      window.location.href = `${API_BASE_URL}/api/download/${zipFilename}`;
      setCurrentStep(3);
    } else {
      setError('Ingen ZIP-fil tilgjengelig for nedlasting');
    }
  };

  const handleCancel = () => {
    setCurrentStep(0);
    setFile(null);
    setParsedSections(null);
    setKeywords([]);
    setZipFilename(null);
    setError(null);
    setIsUploading(false);
    setIsProcessing(false);
    setProcessedSections(0);
    setTotalSections(0);
  };

  const renderStepIndicator = () => (
    <div className="mb-12">
      <div className="flex items-center justify-between">
        {steps.map((step, index) => (
          <div key={step.name} className="flex flex-col items-center">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <div className={`rounded-full transition duration-500 ease-in-out h-20 w-20 flex items-center justify-center border-4 ${
                    index < currentStep ? 'border-green-400 bg-green-900' :
                    index === currentStep ? 'border-blue-400 bg-blue-900' :
                    'border-gray-600 bg-gray-700'
                  }`}>
                    <step.icon size={32} className={
                      index < currentStep ? 'text-green-400' :
                      index === currentStep ? 'text-blue-400' :
                      'text-gray-400'
                    } />
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  {step.description}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <div className="text-center mt-4">
              <span className={`text-sm font-medium ${
                index <= currentStep ? 'text-blue-400' : 'text-gray-500'
              }`}>
                {step.name}
              </span>
            </div>
          </div>
        ))}
      </div>
      <Progress value={(currentStep / (steps.length - 1)) * 100} className="mt-4" />
    </div>
  );

  const renderFileUpload = () => (
    <div className="mt-8 bg-gray-700 p-6 rounded-lg">
      <div {...getRootProps()} className={`flex flex-col items-center px-4 py-6 bg-gray-800 text-blue-400 rounded-lg shadow-lg tracking-wide border-2 border-dashed ${isDragActive ? 'border-blue-400' : 'border-gray-400'} cursor-pointer hover:bg-gray-700 hover:text-blue-300 transition duration-300 ease-in-out`}>
        <input {...getInputProps()} />
        <Upload size={48} />
        <span className="mt-2 text-base leading-normal">
          {isDragActive ? 'Slipp filen her' : 'Dra og slipp en fil her, eller klikk for å velge en fil'}
        </span>
      </div>
      {file && (
        <div className="mt-4 text-gray-300">
          <p>Valgt fil: {file.name}</p>
          <Button
            onClick={handleUploadAndParse}
            className="mt-4 w-full"
            disabled={isUploading}
          >
            {isUploading ? (
              <>
                <Loader className="animate-spin mr-2" size={20} />
                Laster opp og analyserer...
              </>
            ) : (
              <>
                Last opp og analyser <ArrowRight className="ml-2" size={20} />
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );

  const renderProcessingSections = () => (
    <div className="mt-8 bg-gray-700 p-6 rounded-lg">
      <p className="mb-4 text-gray-300">Fil analysert vellykket. Her er et sammendrag av de analyserte seksjonene:</p>
      <ul className="list-disc list-inside mb-4 text-gray-300">
        {parsedSections && parsedSections.map((section, index) => (
          <li key={index}>{section.title || `Seksjon ${index + 1}`}</li>
        ))}
      </ul>
      <p className="mb-4 text-gray-300">Uttrukne nøkkelord: {keywords.join(', ')}</p>
      {isProcessing && (
        <div className="mb-4">
          <Progress value={(processedSections / totalSections) * 100} className="mb-2" />
          <p className="text-center text-gray-300">
            Behandler seksjon {processedSections} av {totalSections}
          </p>
        </div>
      )}
      <Button
        onClick={handleProcessSections}
        className="w-full"
        disabled={isProcessing}
      >
        {isProcessing ? (
          <>
            <Loader className="animate-spin mr-2" size={20} />
            Behandler seksjoner...
          </>
        ) : (
          <>
            Behandle seksjoner <ArrowRight className="ml-2" size={20} />
          </>
        )}
      </Button>
    </div>
  );

  const renderDownload = () => (
    <div className="mt-8 bg-gray-700 p-6 rounded-lg">
      <p className="mb-4 text-gray-300">Seksjoner behandlet. Klikk under for å laste ned ZIP-filen.</p>
      <Button
        onClick={handleDownload}
        className="w-full"
      >
        Last ned ZIP <Download className="ml-2" size={20} />
      </Button>
    </div>
  );

  const renderComplete = () => (
    <div className="mt-8 bg-gray-700 p-6 rounded-lg text-center">
      <CheckCircle size={64} className="mx-auto text-green-400 mb-4" />
      <p className="text-2xl font-semibold text-white">Prosessen er fullført!</p>
      <p className="mt-2 text-gray-300">Filen din er behandlet og ZIP-filen er lastet ned.</p>
      <Button onClick={() => setCurrentStep(0)} className="mt-4">
        Behandle en annen fil
      </Button>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <div className="max-w-4xl w-full bg-gray-800 rounded-lg shadow-xl p-8">
        <h1 className="text-3xl font-bold text-white mb-8 text-center">Dokumentbehandler</h1>

        {renderStepIndicator()}

        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {currentStep === 0 && renderFileUpload()}
        {currentStep === 1 && renderProcessingSections()}
        {currentStep === 2 && renderDownload()}
        {currentStep === 3 && renderComplete()}

        {currentStep > 0 && currentStep < 3 && (
          <Button variant="outline" onClick={handleCancel} className="mt-4">
            Avbryt <X className="ml-2" size={20} />
          </Button>
        )}
      </div>
    </div>
  );
};

export default FileUploadWizard;